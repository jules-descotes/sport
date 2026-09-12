"""Backfill d'une session — archive Open-Meteo mockée.

Le `conditions_snapshot` est la seule décision de modèle irrattrapable après
coup. Ce que ces tests protègent :

- la fenêtre fait bien **trois points** (T−2 h, T−1 h, T0), pas un seul ;
- une session **rétroactive** est traitée exactement comme une session du jour ;
- un spot **jamais ingéré** produit quand même un volet `observed` ;
- un **échec d'archive n'empêche jamais** d'enregistrer la session.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.services import backfill
from app.services.backfill import (
    build_conditions_snapshot,
    window_timestamps,
)
from app.services.forecast_ingest import upsert_forecast_rows
from app.services.openmeteo import HourlyBundle

SESSION_START = datetime(2026, 9, 12, 8, 30, tzinfo=UTC)


def archive_bundle(start: datetime, hours: int = 48) -> HourlyBundle:
    """Journée complète d'archive : c'est ce que renvoie vraiment Open-Meteo."""
    import math

    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return HourlyBundle(
        rows={
            day_start
            + timedelta(hours=hour): {
                # Houle montante sur la fenêtre : la tendance doit se voir.
                "wave_height_m": round(1.0 + 0.05 * hour, 3),
                "wave_period_s": 11.0,
                "wave_peak_period_s": 12.0,
                "wave_direction_deg": 285.0,
                "wind_speed_kt": round(5.0 + 0.5 * hour, 3),
                "wind_gust_kt": 12.0,
                "wind_direction_deg": 90.0,
                "sea_level_m": round(1.8 * math.sin(2 * math.pi * hour / 12.42), 3),
                "water_temperature_c": 19.0,
            }
            for hour in range(hours)
        }
    )


@pytest.fixture
def fake_archive(monkeypatch):
    """Remplace l'appel d'archive. Aucun test ne sort sur le réseau."""

    def _install(bundle=None, fail: bool = False):
        calls: list[tuple[float, float]] = []

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc_info):
                return None

            async def fetch_archive(self, lat, lon, start, end):
                calls.append((lat, lon))
                if fail:
                    raise httpx.ConnectError("archive injoignable")
                return bundle if bundle is not None else archive_bundle(SESSION_START)

        monkeypatch.setattr(backfill, "OpenMeteoClient", FakeClient)
        return calls

    return _install


# ── Fenêtre ────────────────────────────────────────────────────────────────


def test_window_is_three_hours_aligned_on_the_hour() -> None:
    """Open-Meteo est horaire : on ne feint pas une précision qui n'existe pas."""
    timestamps = window_timestamps(SESSION_START)

    assert timestamps == [
        datetime(2026, 9, 12, 6, tzinfo=UTC),
        datetime(2026, 9, 12, 7, tzinfo=UTC),
        datetime(2026, 9, 12, 8, tzinfo=UTC),
    ]


def test_window_handles_a_session_across_midnight() -> None:
    timestamps = window_timestamps(datetime(2026, 9, 12, 0, 45, tzinfo=UTC))
    assert timestamps[0] == datetime(2026, 9, 11, 22, tzinfo=UTC)


# ── Volet observed ─────────────────────────────────────────────────────────


async def test_observed_panel_has_the_three_points(
    db_session, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()

    snapshot = await build_conditions_snapshot(db_session, spot, SESSION_START)

    assert [entry["offset_h"] for entry in snapshot["observed"]] == [-2, -1, 0]
    assert snapshot["observed"][0]["wave_height_m"] == pytest.approx(1.3)
    assert snapshot["observed"][-1]["wave_height_m"] == pytest.approx(1.4)


async def test_backfill_works_on_a_spot_never_ingested(
    db_session, make_spot, fake_archive
) -> None:
    """Spot de voyage : aucune prévision en base, mais l'archive répond quand même."""
    calls = fake_archive()
    spot = await make_spot(name="Uluwatu", slug="uluwatu", lat=-8.82, lon=115.09)

    snapshot = await build_conditions_snapshot(db_session, spot, SESSION_START)

    assert calls == [(spot.lat, spot.lon)]
    assert len(snapshot["observed"]) == 3
    # Rien n'a été ingéré pour ce spot : le volet prévision est vide, et c'est
    # normal — la prévision de la veille n'est pas reconstituable.
    assert snapshot["forecast"] == []


async def test_retroactive_session_is_backfilled_like_any_other(
    db_session, make_spot, fake_archive
) -> None:
    """Une session saisie six mois plus tard produit le même snapshot."""
    past = datetime(2026, 3, 4, 9, 0, tzinfo=UTC)
    fake_archive(bundle=archive_bundle(past))
    spot = await make_spot()

    snapshot = await build_conditions_snapshot(db_session, spot, past)

    assert len(snapshot["observed"]) == 3
    assert snapshot["reference_ts"] == "2026-03-04T09:00:00+00:00"


# ── Volet forecast ─────────────────────────────────────────────────────────


async def test_forecast_panel_comes_from_the_ingested_rows(
    db_session, make_spot, fake_archive
) -> None:
    """Sur un spot maison, ce qui était annoncé est conservé à côté du constaté."""
    fake_archive()
    spot = await make_spot()

    await upsert_forecast_rows(
        db_session,
        spot.id,
        HourlyBundle(
            rows={
                ts: {"wave_height_m": 0.9, "wind_speed_kt": 4.0}
                for ts in window_timestamps(SESSION_START)
            }
        ),
    )

    snapshot = await build_conditions_snapshot(db_session, spot, SESSION_START)

    assert len(snapshot["forecast"]) == 3
    assert all(entry["wave_height_m"] == 0.9 for entry in snapshot["forecast"])
    # Les deux volets restent distincts : prévision et constat ne se mélangent pas.
    assert snapshot["observed"][0]["wave_height_m"] != 0.9


# ── Tendances ──────────────────────────────────────────────────────────────


async def test_trends_capture_a_rising_swell(
    db_session, make_spot, fake_archive
) -> None:
    """Une houle de 1,4 m qui monte et une qui s'écroule ne sont pas la même session."""
    fake_archive()
    spot = await make_spot()

    snapshot = await build_conditions_snapshot(db_session, spot, SESSION_START)

    assert snapshot["trends"]["observed"]["wave_height_m"] == pytest.approx(0.1)
    assert snapshot["trends"]["observed"]["wind_speed_kt"] == pytest.approx(1.0)


async def test_tide_is_read_on_the_whole_day(
    db_session, make_spot, fake_archive
) -> None:
    """Trois points ne disent pas où sont la pleine et la basse mer."""
    fake_archive()
    spot = await make_spot()

    snapshot = await build_conditions_snapshot(db_session, spot, SESSION_START)

    assert snapshot["tide"]["range_m"] == pytest.approx(3.6, abs=0.1)
    assert 0.0 <= snapshot["tide"]["position"] <= 1.0


# ── Robustesse ─────────────────────────────────────────────────────────────


async def test_archive_failure_never_loses_the_session(
    db_session, make_spot, fake_archive
) -> None:
    """Perdre une session pour un timeout serait le comble : le risque du projet
    est la friction de saisie, pas la rareté des données."""
    fake_archive(fail=True)
    spot = await make_spot()

    snapshot = await build_conditions_snapshot(db_session, spot, SESSION_START)

    assert snapshot["observed"] == []
    assert snapshot["observed_error"]
    assert snapshot["reference_ts"]


async def test_snapshot_records_the_model_version(
    db_session, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()

    snapshot = await build_conditions_snapshot(db_session, spot, SESSION_START)

    assert snapshot["model"] == "meteofrance_wave"
    assert snapshot["model_version"]
    assert snapshot["spot"]["onshore_dir_deg"] == 270.0


# ── Bout en bout par l'API ─────────────────────────────────────────────────


async def test_create_session_freezes_the_snapshot(
    auth_client, db_session, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions",
        json={
            "spot_id": spot.id,
            "started_at": SESSION_START.isoformat(),
            "duration_min": 90,
            "rating_conditions": 4,
            "rating_personal": 5,
        },
    )

    assert response.status_code == 201
    body = response.json()
    # Deux notes distinctes, jamais une seule.
    assert body["rating_conditions"] == 4
    assert body["rating_personal"] == 5
    assert len(body["conditions_snapshot"]["observed"]) == 3
    assert body["conditions_snapshot"]["window_hours"] == [-2, -1, 0]


async def test_create_session_on_unknown_spot_is_rejected(
    auth_client, fake_archive
) -> None:
    fake_archive()
    response = await auth_client.post(
        "/api/v1/sessions",
        json={"spot_id": 9999, "started_at": SESSION_START.isoformat()},
    )
    assert response.status_code == 404
