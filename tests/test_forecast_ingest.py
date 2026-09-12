"""Ingestion : idempotence, cache de trois heures, plafond d'appels.

Le conteneur Railway redémarre à froid et le job repart du début : c'est le
scénario à tenir, pas un cas limite.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional

import httpx
import pytest
from sqlalchemy import func, select

from app.models.enums import SpotTier
from app.models.forecast import Forecast
from app.services import forecast_ingest
from app.services.forecast_ingest import (
    ensure_fresh,
    ingest_forecasts,
    refresh_spots,
    stale_spot_ids,
    upsert_forecast_rows,
)
from app.services.openmeteo import (
    CallBudget,
    CallBudgetExhausted,
    HourlyBundle,
    OpenMeteoClient,
    parse_hourly,
)

TS = datetime(2026, 9, 12, 6, 0, tzinfo=UTC)


def bundle(hours: int = 3, wave_height_m: float = 1.4) -> HourlyBundle:
    return HourlyBundle(
        rows={
            TS
            + timedelta(hours=hour): {
                "wave_height_m": wave_height_m,
                "wave_period_s": 12.0,
                "wave_direction_deg": 285.0,
                "wind_speed_kt": 8.0,
                "wind_direction_deg": 90.0,
                "sea_level_m": 0.5,
            }
            for hour in range(hours)
        }
    )


async def _count(db) -> int:
    return (await db.execute(select(func.count()).select_from(Forecast))).scalar_one()


# ── Idempotence ────────────────────────────────────────────────────────────


async def test_upsert_writes_rows(db_session, make_spot) -> None:
    spot = await make_spot()

    written = await upsert_forecast_rows(db_session, spot.id, bundle(hours=5))

    assert written == 5
    assert await _count(db_session) == 5


async def test_upsert_is_idempotent(db_session, make_spot) -> None:
    """Le job rejoué ne duplique jamais une heure déjà ingérée."""
    spot = await make_spot()

    await upsert_forecast_rows(db_session, spot.id, bundle(hours=5))
    await upsert_forecast_rows(db_session, spot.id, bundle(hours=5))
    await upsert_forecast_rows(db_session, spot.id, bundle(hours=5))

    assert await _count(db_session) == 5


async def test_upsert_updates_revised_values(db_session, make_spot) -> None:
    """Une prévision révisée écrase l'ancienne, elle ne s'ajoute pas à côté."""
    spot = await make_spot()

    await upsert_forecast_rows(db_session, spot.id, bundle(wave_height_m=1.4))
    await upsert_forecast_rows(db_session, spot.id, bundle(wave_height_m=2.1))

    heights = (
        (await db_session.execute(select(Forecast.wave_height_m))).scalars().all()
    )
    assert set(heights) == {2.1}


async def test_upsert_stores_source_and_model_version(db_session, make_spot) -> None:
    """Les modèles de vagues sont recalibrés : sans version, l'historique est perdu."""
    spot = await make_spot()
    await upsert_forecast_rows(db_session, spot.id, bundle(hours=1))

    forecast = (await db_session.execute(select(Forecast))).scalar_one()
    assert forecast.source == "open-meteo"
    assert forecast.model == "meteofrance_wave"
    assert forecast.model_version


async def test_two_spots_do_not_collide(db_session, make_spot) -> None:
    """La clé est (spot, heure, source) : deux spots à la même heure coexistent."""
    first = await make_spot(name="La Gravière", slug="la-graviere")
    second = await make_spot(name="Les Culs Nus", slug="les-culs-nus", lat=43.70)

    await upsert_forecast_rows(db_session, first.id, bundle(hours=3))
    await upsert_forecast_rows(db_session, second.id, bundle(hours=3))

    assert await _count(db_session) == 6


# ── Cache de trois heures ──────────────────────────────────────────────────


async def test_fresh_cache_is_not_stale(db_session, make_spot, make_forecast) -> None:
    spot = await make_spot()
    await make_forecast(spot, fetched_at=datetime.now(UTC) - timedelta(minutes=30))

    assert await stale_spot_ids(db_session, [spot.id]) == []


async def test_cache_older_than_three_hours_is_stale(
    db_session, make_spot, make_forecast
) -> None:
    spot = await make_spot()
    await make_forecast(spot, fetched_at=datetime.now(UTC) - timedelta(hours=3, minutes=1))

    assert await stale_spot_ids(db_session, [spot.id]) == [spot.id]


async def test_never_fetched_spot_is_stale(db_session, make_spot) -> None:
    spot = await make_spot()
    assert await stale_spot_ids(db_session, [spot.id]) == [spot.id]


async def test_stale_check_separates_fresh_from_stale(
    db_session, make_spot, make_forecast
) -> None:
    fresh = await make_spot(name="Frais", slug="frais")
    stale = await make_spot(name="Vieux", slug="vieux", lat=43.70)
    await make_forecast(fresh, fetched_at=datetime.now(UTC))
    await make_forecast(stale, fetched_at=datetime.now(UTC) - timedelta(hours=5))

    assert await stale_spot_ids(db_session, [fresh.id, stale.id]) == [stale.id]


# ── Récupération ───────────────────────────────────────────────────────────


class FakeClient:
    """Remplace `OpenMeteoClient` : compte les appels, ne sort jamais du process."""

    def __init__(self, budget: Optional[CallBudget] = None, fail_for: tuple = ()) -> None:
        self.budget = budget or CallBudget()
        self.calls: list[tuple[float, float]] = []
        self.fail_for = fail_for

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def fetch_forecast(self, lat: float, lon: float, forecast_days: int = 5):
        # Un appel réel en consomme trois : houle, mer, vent.
        for _ in range(3):
            self.budget.take()
        self.calls.append((lat, lon))
        if lat in self.fail_for:
            raise httpx.ConnectError("Open-Meteo injoignable")
        return bundle(hours=6)


@pytest.fixture
def fake_openmeteo(monkeypatch):
    created: list[FakeClient] = []

    def _install(**kwargs):
        def factory(budget=None, **_):
            client = FakeClient(budget=budget, **kwargs)
            created.append(client)
            return client

        monkeypatch.setattr(forecast_ingest, "OpenMeteoClient", factory)
        return created

    return _install


async def test_refresh_spots_writes_forecasts(
    db_session, make_spot, fake_openmeteo
) -> None:
    created = fake_openmeteo()
    spot = await make_spot()

    done = await refresh_spots(db_session, [spot])

    assert done == 1
    assert created[0].calls == [(spot.lat, spot.lon)]
    assert await _count(db_session) == 6


async def test_one_failing_spot_does_not_stop_the_pass(
    db_session, make_spot, fake_openmeteo
) -> None:
    """La mer sera toujours là dans trois heures : on continue la passe."""
    broken = await make_spot(name="Cassé", slug="casse", lat=1.0, lon=1.0)
    working = await make_spot(name="Bon", slug="bon")
    fake_openmeteo(fail_for=(broken.lat,))

    done = await refresh_spots(db_session, [broken, working])

    assert done == 1
    assert await _count(db_session) == 6


async def test_call_budget_stops_the_pass(db_session, make_spot, fake_openmeteo) -> None:
    """Garde-fou contre une boucle qui partirait sur le catalogue mondial."""
    fake_openmeteo()
    spots = [
        await make_spot(name=f"Spot {i}", slug=f"spot-{i}", lat=43.0 + i / 100)
        for i in range(5)
    ]

    budget = CallBudget(limit=7)  # de quoi traiter deux spots, pas trois
    done = await refresh_spots(db_session, spots, budget)

    assert done == 2
    assert budget.remaining == 0


def test_budget_raises_once_exhausted() -> None:
    budget = CallBudget(limit=2)
    budget.take()
    budget.take()
    with pytest.raises(CallBudgetExhausted):
        budget.take()


# ── Passe planifiée ────────────────────────────────────────────────────────


async def test_scheduled_pass_only_touches_home_spots(
    db_session, make_spot, fake_openmeteo, patch_session_factory
) -> None:
    """« Jamais tous les spots tout le temps » : le job ne voit que les favoris."""
    created = fake_openmeteo()
    patch_session_factory(forecast_ingest, db_session)

    home = await make_spot(name="Maison", slug="maison", tier=SpotTier.HOME.value)
    await make_spot(
        name="Potentiel", slug="potentiel", lat=43.70, tier=SpotTier.POTENTIAL.value
    )
    await make_spot(
        name="Catalogue", slug="catalogue", lat=43.80, tier=SpotTier.CATALOG.value
    )

    await ingest_forecasts()

    assert created[0].calls == [(home.lat, home.lon)]


async def test_scheduled_pass_without_home_spots_calls_nothing(
    db_session, make_spot, fake_openmeteo, patch_session_factory
) -> None:
    """Zéro appel tant que personne n'a mis de favori."""
    created = fake_openmeteo()
    patch_session_factory(forecast_ingest, db_session)
    await make_spot(tier=SpotTier.POTENTIAL.value)

    await ingest_forecasts()

    assert created == []


# ── À la demande : les cinq secondes ───────────────────────────────────────


async def test_ensure_fresh_skips_when_cache_is_warm(
    db_session, make_spot, make_forecast, monkeypatch
) -> None:
    spot = await make_spot()
    await make_forecast(spot, fetched_at=datetime.now(UTC))

    called: list[list[int]] = []

    async def _never(spot_ids):
        called.append(list(spot_ids))
        return 0

    monkeypatch.setattr(forecast_ingest, "refresh_spot_ids_detached", _never)

    assert await ensure_fresh(db_session, [spot]) == []
    assert called == []


async def test_ensure_fresh_waits_for_a_quick_refresh(
    db_session, make_spot, monkeypatch
) -> None:
    spot = await make_spot()

    async def _quick(spot_ids):
        return len(list(spot_ids))

    monkeypatch.setattr(forecast_ingest, "refresh_spot_ids_detached", _quick)

    # Rien à signaler : la récupération a tenu dans le délai.
    assert await ensure_fresh(db_session, [spot]) == []


async def test_ensure_fresh_serves_the_database_when_openmeteo_is_slow(
    db_session, make_spot, monkeypatch
) -> None:
    """Un écran d'accueil à huit secondes ne sera pas ouvert deux fois."""
    import asyncio

    spot = await make_spot()
    finished = asyncio.Event()

    async def _slow(spot_ids):
        await asyncio.sleep(0.3)
        finished.set()
        return len(list(spot_ids))

    monkeypatch.setattr(forecast_ingest, "refresh_spot_ids_detached", _slow)

    refreshing = await ensure_fresh(db_session, [spot], timeout_s=0.05)

    assert refreshing == [spot.id]
    # La récupération n'est pas annulée : elle se termine derrière.
    await asyncio.wait_for(finished.wait(), timeout=2.0)


# ── Lecture des réponses Open-Meteo ────────────────────────────────────────


def test_parse_hourly_transposes_open_meteo_columns() -> None:
    payload = {
        "hourly": {
            "time": ["2026-09-12T06:00", "2026-09-12T07:00"],
            "wave_height": [1.4, 1.5],
            "wave_peak_period": [12.0, 12.5],
            "sea_level_height_msl": [0.4, 0.9],
            "wind_speed_10m": [8.0, None],
        }
    }
    rows = parse_hourly(payload).rows

    assert set(rows) == {
        datetime(2026, 9, 12, 6, tzinfo=UTC),
        datetime(2026, 9, 12, 7, tzinfo=UTC),
    }
    first = rows[datetime(2026, 9, 12, 6, tzinfo=UTC)]
    assert first["wave_height_m"] == 1.4
    assert first["wave_peak_period_s"] == 12.0
    assert first["sea_level_m"] == 0.4
    # Un trou de données reste un trou, il ne devient pas zéro.
    assert rows[datetime(2026, 9, 12, 7, tzinfo=UTC)]["wind_speed_kt"] is None


def test_parse_hourly_on_empty_payload() -> None:
    assert parse_hourly({}).rows == {}


async def test_client_retries_on_429_then_succeeds(monkeypatch) -> None:
    """Backoff exponentiel sur 429, en respectant `Retry-After`."""
    import asyncio

    attempts = {"count": 0}
    slept: list[float] = []

    async def _no_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"hourly": {"time": []}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OpenMeteoClient(client=http_client)
        payload = await client._get("https://example.invalid/marine", {})

    assert attempts["count"] == 2
    assert slept == [2.0]
    assert payload == {"hourly": {"time": []}}
    # Le plafond compte la requête, pas les tentatives.
    assert client.budget.used == 1
