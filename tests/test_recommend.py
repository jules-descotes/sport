"""`/recommend` — l'écran d'accueil tient dans cet appel.

« Je vais à l'eau, oui ou non, et où ? » : un verdict, un spot, un créneau, et
la grille complète pour le comparateur. Le tout en un aller-retour.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.enums import SpotTier
from app.services.recommend import build_sentence, recommend
from tests.conftest import HOSSEGOR_LAT, HOSSEGOR_LON


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Aucun test de recommandation ne sort sur le réseau.

    Les prévisions sont posées en base par les fixtures ; si un test en oublie,
    le rafraîchissement est un non-événement plutôt qu'un appel réel.
    """
    from app.services import forecast_ingest

    async def _no_refresh(spot_ids):
        return 0

    monkeypatch.setattr(forecast_ingest, "refresh_spot_ids_detached", _no_refresh)


# ── Service ────────────────────────────────────────────────────────────────


async def test_recommend_scores_every_slot(
    db_session, preferences, make_spot, make_forecast
) -> None:
    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value)
    await make_forecast(spot)

    result = await recommend(db_session, preferences, HOSSEGOR_LAT, HOSSEGOR_LON)

    slots = result.spots[0].slots
    assert len(result.spots) == 1
    # Tous les créneaux sont rendus, nuit comprise : la bande de l'écran Jour
    # est une matrice, une colonne manquante décale toute la lecture.
    assert len(slots) == 48
    # Mais la nuit est marquée, et le meilleur créneau n'y tombe jamais.
    assert any(not slot.daylight for slot in slots)
    assert result.spots[0].best.daylight
    assert result.headline is None or result.headline.daylight


async def test_the_whole_day_is_served_not_only_what_is_left(
    db_session, preferences, make_spot, make_forecast
) -> None:
    """La bande de l'écran Jour part de **ce matin**, pas de l'heure courante.

    La fenêtre s'ouvrait à `now - 2 h` : à 14 h, les quatre premières colonnes
    de la bande étaient vides alors que la matinée était en base. On la montre
    désormais en entier — mais on continue de ne conseiller que l'avenir.
    """
    zone = ZoneInfo("Europe/Paris")
    now = datetime(2026, 9, 13, 14, 20, tzinfo=zone).astimezone(UTC)
    day_start = datetime(2026, 9, 13, 0, 0, tzinfo=zone).astimezone(UTC)

    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value)
    await make_forecast(
        spot, start=day_start, hours=48, fetched_at=now, run_ts=day_start
    )

    result = await recommend(
        db_session,
        preferences,
        HOSSEGOR_LAT,
        HOSSEGOR_LON,
        timezone="Europe/Paris",
        now=now,
        refresh=False,
    )

    today = now.astimezone(zone).date()
    hours = {
        slot.ts.astimezone(zone).hour
        for slot in result.spots[0].slots
        if slot.ts.astimezone(zone).date() == today
    }
    # Les huit colonnes de la bande, matinée comprise.
    assert {0, 3, 6, 9, 12, 15, 18, 21} <= hours

    # Et le conseil, lui, ne regarde pas en arrière : proposer 9 h à 14 h 20
    # serait pire que de ne rien proposer.
    assert result.spots[0].best is not None
    assert result.spots[0].best.ts >= now - timedelta(minutes=30)
    assert result.headline is None or result.headline.ts >= now - timedelta(minutes=30)


async def test_a_slot_before_midnight_survives_the_small_hours(
    db_session, preferences, make_spot, make_forecast
) -> None:
    """À 0 h 30, le début de journée locale est *postérieur* à `now - 2 h`.

    Sans le repli, élargir à la journée aurait **rétréci** la fenêtre au moment
    exact où l'on regarde encore la soirée qui vient de finir.
    """
    zone = ZoneInfo("Europe/Paris")
    now = datetime(2026, 9, 13, 0, 30, tzinfo=zone).astimezone(UTC)

    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value)
    await make_forecast(
        spot,
        start=now - timedelta(hours=6),
        hours=48,
        fetched_at=now,
        run_ts=now - timedelta(hours=6),
    )

    result = await recommend(
        db_session,
        preferences,
        HOSSEGOR_LAT,
        HOSSEGOR_LON,
        timezone="Europe/Paris",
        now=now,
        refresh=False,
    )

    earliest = min(slot.ts for slot in result.spots[0].slots)
    assert earliest <= now - timedelta(hours=2)


async def test_recommend_ranks_the_best_spot_first(
    db_session, preferences, make_spot, make_forecast
) -> None:
    clean = await make_spot(
        name="Propre", slug="propre", lat=HOSSEGOR_LAT + 0.01,
        tier=SpotTier.HOME.value,
    )
    messy = await make_spot(
        name="Sale", slug="sale", lat=HOSSEGOR_LAT + 0.02,
        tier=SpotTier.POTENTIAL.value,
    )
    await make_forecast(clean, wave_height_m=1.5, wave_period_s=13, wind_direction_deg=90)
    await make_forecast(messy, wave_height_m=0.2, wave_period_s=5, wind_speed_kt=25,
                        wind_direction_deg=270)

    result = await recommend(db_session, preferences, HOSSEGOR_LAT, HOSSEGOR_LON)

    assert [item.spot.slug for item in result.spots] == ["propre", "sale"]
    assert result.headline_spot.slug == "propre"
    assert result.verdict == "OUI"


async def test_catalog_spots_are_never_recommended(
    db_session, preferences, make_spot, make_forecast
) -> None:
    """Ils n'ont pas de prévision et n'en auront pas."""
    catalog = await make_spot(
        name="Catalogue", slug="catalogue", lat=HOSSEGOR_LAT + 0.01,
        tier=SpotTier.CATALOG.value,
    )
    await make_forecast(catalog)

    result = await recommend(db_session, preferences, HOSSEGOR_LAT, HOSSEGOR_LON)

    assert result.spots == []


async def test_hidden_spots_are_excluded(
    db_session, preferences, make_spot, make_forecast
) -> None:
    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.POTENTIAL.value)
    await make_forecast(spot)
    preferences.hidden_spot_ids = [spot.id]
    await db_session.commit()

    result = await recommend(db_session, preferences, HOSSEGOR_LAT, HOSSEGOR_LON)

    assert result.spots == []


async def test_falls_back_to_home_when_geolocation_is_refused(
    db_session, preferences, make_spot, make_forecast
) -> None:
    """Un refus de géolocalisation ne doit jamais donner un écran vide."""
    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value)
    await make_forecast(spot)

    result = await recommend(db_session, preferences, lat=None, lon=None)

    assert result.position_source == "home"
    assert len(result.spots) == 1


async def test_without_home_or_position_the_screen_says_so(
    db_session, user
) -> None:
    from app.services.spot_tiers import get_or_create_preferences

    preferences = await get_or_create_preferences(db_session, user.id)
    result = await recommend(db_session, preferences, lat=None, lon=None)

    assert result.position_source == "unknown"
    assert "domicile" in result.sentence


async def test_verdict_is_no_when_the_sea_is_flat(
    db_session, preferences, make_spot, make_forecast
) -> None:
    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value)
    await make_forecast(spot, wave_height_m=0.15, wave_period_s=5.0)

    result = await recommend(db_session, preferences, HOSSEGOR_LAT, HOSSEGOR_LON)

    assert result.verdict == "NON"


async def test_spots_beyond_the_radius_are_ignored(
    db_session, preferences, make_spot, make_forecast
) -> None:
    far = await make_spot(
        name="Nazaré", slug="nazare", lat=39.60, lon=-9.07,
        tier=SpotTier.HOME.value,
    )
    await make_forecast(far)

    result = await recommend(db_session, preferences, HOSSEGOR_LAT, HOSSEGOR_LON)

    assert result.spots == []


# ── Phrase d'explication ───────────────────────────────────────────────────


def test_sentence_reads_like_the_target_output(make_spot) -> None:
    """« Demain 8 h — Les Cavaliers, 4,2/5 · houle 1,4 m / 12 s / NO, vent E 8 kt »."""
    from app.models.spot import Spot
    from app.services.recommend import Slot
    from app.services.scoring import Conditions, score_conditions

    spot = Spot(slug="les-cavaliers", name="Les Cavaliers", lat=43.52, lon=-1.53,
                onshore_dir_deg=270.0)
    ts = datetime(2026, 9, 13, 6, 0, tzinfo=UTC)  # 8 h heure de Paris
    conditions = Conditions(
        ts=ts,
        wave_height_m=1.4,
        wave_period_s=12.0,
        wave_direction_deg=315.0,
        wind_speed_kt=8.0,
        wind_direction_deg=90.0,
        tide_position=0.5,
        tide_trend_m_per_h=0.3,
    )
    slot = Slot(
        ts=ts,
        conditions=conditions,
        score=score_conditions(conditions, spot.onshore_dir_deg),
        daylight=True,
    )

    sentence = build_sentence(
        spot, slot, now=datetime(2026, 9, 12, 10, tzinfo=UTC), timezone="Europe/Paris"
    )

    assert sentence.startswith("Demain 8 h — Les Cavaliers, ")
    assert "houle 1,4 m / 12 s / NO" in sentence
    assert "vent E 8 kt" in sentence
    assert "marée montante" in sentence


def test_sentence_without_a_spot_is_still_a_sentence() -> None:
    sentence = build_sentence(None, None, now=datetime(2026, 9, 12, tzinfo=UTC))
    assert sentence and sentence[0].isupper()


# ── Route ──────────────────────────────────────────────────────────────────


async def test_recommend_endpoint_serves_home_and_comparator(
    auth_client, db_session, make_spot, make_forecast
) -> None:
    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value)
    await make_forecast(spot, fetched_at=datetime.now(UTC))

    response = await auth_client.get(
        "/api/v1/recommend", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )

    assert response.status_code == 200
    body = response.json()

    # L'écran d'accueil : un verdict, un spot, une phrase.
    assert body["verdict"] in {"OUI", "NON", "PEUT-ÊTRE"}
    assert body["headline_spot"]["slug"] == spot.slug
    assert body["sentence"]
    assert body["position_source"] == "device"

    # Le comparateur : la grille heures × spots, dans la même réponse.
    slots = body["spots"][0]["slots"]
    assert slots
    assert all(1 <= slot["level"] <= 5 for slot in slots)
    assert all(slot["line"] for slot in slots)


async def test_recommend_records_the_position(
    auth_client, db_session, make_spot, make_forecast
) -> None:
    """Le mode trip ne doit pas avoir un tour de retard."""
    away = await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)
    await make_forecast(away, fetched_at=datetime.now(UTC))

    response = await auth_client.get(
        "/api/v1/recommend", params={"lat": 39.61, "lon": -9.08}
    )

    assert response.status_code == 200
    await db_session.refresh(away)
    assert away.tier == SpotTier.POTENTIAL.value
    assert [item["spot"]["slug"] for item in response.json()["spots"]] == ["nazare"]


async def test_recommend_requires_authentication(client) -> None:
    assert (await client.get("/api/v1/recommend")).status_code == 401


async def test_recommend_survives_a_spot_without_forecast(
    auth_client, make_spot, make_forecast
) -> None:
    """Un spot potentiel jamais ingéré ne doit pas casser l'écran d'accueil."""
    with_forecast = await make_spot(
        name="Avec", slug="avec", lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value
    )
    await make_forecast(with_forecast, fetched_at=datetime.now(UTC))
    await make_spot(
        name="Sans", slug="sans", lat=HOSSEGOR_LAT + 0.02,
        tier=SpotTier.POTENTIAL.value,
    )

    await auth_client.put(
        "/api/v1/spots/preferences",
        json={"home_lat": HOSSEGOR_LAT, "home_lon": HOSSEGOR_LON, "radius_km": 40},
    )
    response = await auth_client.get(
        "/api/v1/recommend", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )

    assert response.status_code == 200
    by_slug = {item["spot"]["slug"]: item for item in response.json()["spots"]}
    assert by_slug["sans"]["slots"] == []
    assert by_slug["sans"]["best"] is None


async def test_stale_forecast_does_not_block_the_response(
    auth_client, make_spot, make_forecast, monkeypatch
) -> None:
    """Au-delà de cinq secondes, on sert la base et on complète derrière."""
    import asyncio

    from app.services import forecast_ingest

    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01, tier=SpotTier.HOME.value)
    await make_forecast(spot, fetched_at=datetime.now(UTC) - timedelta(hours=4))
    # Depuis le lot 1 ter, `/recommend` n'ingère que le spot favori : sans lui,
    # l'appel ne déclenche plus rien du tout — et c'est exactement le but.
    await auth_client.put("/api/v1/auth/me/profile", json={"home_spot_id": spot.id})

    async def _slow(spot_ids):
        await asyncio.sleep(0.5)
        return 0

    monkeypatch.setattr(forecast_ingest, "refresh_spot_ids_detached", _slow)
    monkeypatch.setattr(
        forecast_ingest.settings, "forecast_on_demand_timeout_s", 0.05
    )

    response = await auth_client.get(
        "/api/v1/recommend", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["refreshing"] == [spot.id]
    # La réponse est servie depuis la base, pas vide.
    assert body["spots"][0]["slots"]
