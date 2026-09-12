"""`run_ts` — historisation des runs, lecture du dernier, écart depuis la veille.

Trois propriétés, et ce sont les trois raisons d'être du lot 1 ter :

1. deux runs sur le même créneau **coexistent** — une passe n'écrase jamais une
   prévision antérieure ;
2. toute lecture « dernière prévision » rend **le run le plus récent**, jamais
   le premier venu ni les deux ;
3. l'écart entre le dernier run et celui de la veille au soir est **juste**,
   directions comprises.

Sans (1), (2) et (3) n'existent pas et chaque jour d'ingestion est perdu
définitivement (cf. PROJET.md §7.3).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.forecast import Forecast
from app.services.forecast_ingest import upsert_forecast_rows
from app.services.forecast_reads import (
    forecast_delta,
    latest_forecasts_select,
    latest_run_ts,
    previous_evening_cutoff,
    signed_angle_delta,
)
from app.services.openmeteo import HourlyBundle
from app.services.recommend import load_forecast_rows

# Le créneau observé : demain 8 h.
SLOT = datetime(2026, 9, 13, 8, 0, tzinfo=UTC)

# Deux runs successifs. 18 h UTC le 12 = 20 h à Paris : le run « de la veille
# au soir », celui qu'on avait sous les yeux avant de se coucher.
RUN_EVENING = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
RUN_MORNING = datetime(2026, 9, 13, 6, 0, tzinfo=UTC)

# « Maintenant » pour les tests : le lendemain matin, après la passe de 6 h.
NOW = datetime(2026, 9, 13, 7, 30, tzinfo=UTC)


def bundle(
    hours: int = 3,
    wave_height_m: float = 1.4,
    wave_period_s: float = 11.0,
    wave_direction_deg: float = 290.0,
    wind_speed_kt: float = 8.0,
    start: datetime = SLOT,
) -> HourlyBundle:
    return HourlyBundle(
        rows={
            start
            + timedelta(hours=hour): {
                "wave_height_m": wave_height_m,
                "wave_period_s": wave_period_s,
                "wave_direction_deg": wave_direction_deg,
                "wind_speed_kt": wind_speed_kt,
                "wind_direction_deg": 90.0,
                "sea_level_m": 0.5,
            }
            for hour in range(hours)
        }
    )


async def _write_two_runs(db, spot) -> None:
    """La veille au soir annonçait 1,2 m ; ce matin annonce 1,8 m."""
    await upsert_forecast_rows(
        db,
        spot.id,
        bundle(wave_height_m=1.2, wave_period_s=10.0, wave_direction_deg=350.0),
        run_ts=RUN_EVENING,
    )
    await upsert_forecast_rows(
        db,
        spot.id,
        bundle(wave_height_m=1.8, wave_period_s=13.0, wave_direction_deg=10.0),
        run_ts=RUN_MORNING,
    )


# ── 1. Les deux runs coexistent ────────────────────────────────────────────


async def test_both_runs_are_kept(db_session, make_spot) -> None:
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    total = (
        await db_session.execute(select(func.count()).select_from(Forecast))
    ).scalar_one()
    # Trois heures × deux runs : rien n'a été écrasé.
    assert total == 6

    on_the_slot = (
        await db_session.execute(
            select(Forecast.wave_height_m).where(Forecast.ts == SLOT)
        )
    ).scalars().all()
    assert sorted(on_the_slot) == [1.2, 1.8]


# ── 2. La lecture rend le run le plus récent ───────────────────────────────


async def test_latest_run_select_returns_only_the_newest(
    db_session, make_spot
) -> None:
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    rows = (
        (await db_session.execute(latest_forecasts_select([spot.id])))
        .scalars()
        .all()
    )

    assert len(rows) == 3  # une ligne par heure, pas deux
    assert {row.wave_height_m for row in rows} == {1.8}
    assert {row.run_ts.replace(tzinfo=UTC) for row in rows} == {RUN_MORNING}


async def test_latest_run_ts_is_the_max(db_session, make_spot) -> None:
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    assert await latest_run_ts(db_session, spot.id) == RUN_MORNING


async def test_an_older_run_never_resurfaces(db_session, make_spot) -> None:
    """Un run plus ancien écrit *après* coup ne devient pas la dernière prévision."""
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    # Rattrapage tardif d'une passe manquée : elle s'ajoute, elle ne prend pas
    # la place du run du matin.
    await upsert_forecast_rows(
        db_session,
        spot.id,
        bundle(wave_height_m=0.4),
        run_ts=RUN_EVENING - timedelta(hours=6),
    )

    rows = (
        (await db_session.execute(latest_forecasts_select([spot.id])))
        .scalars()
        .all()
    )
    assert {row.wave_height_m for row in rows} == {1.8}


async def test_recommend_reads_the_latest_run_only(db_session, make_spot) -> None:
    """La grille de l'écran Mer ne doit pas alterner deux runs d'une cellule à l'autre."""
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    rows = await load_forecast_rows(
        db_session, [spot.id], SLOT - timedelta(hours=1), SLOT + timedelta(hours=6)
    )

    values = rows[spot.id]
    assert len(values) == 3
    assert {entry["wave_height_m"] for _, entry in values} == {1.8}


async def test_spot_forecast_endpoint_serves_one_run(
    auth_client, db_session, make_spot
) -> None:
    """De bout en bout : une heure, une valeur, celle du dernier run."""
    spot = await make_spot()
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    await upsert_forecast_rows(
        db_session, spot.id, bundle(wave_height_m=0.6, start=start), run_ts=RUN_EVENING
    )
    await upsert_forecast_rows(
        db_session, spot.id, bundle(wave_height_m=2.2, start=start), run_ts=RUN_MORNING
    )

    response = await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")

    assert response.status_code == 200
    body = response.json()
    points = body["points"]
    assert len(points) == 3
    assert {point["wave_height_m"] for point in points} == {2.2}
    assert body["run_ts"].startswith("2026-09-13T06:00")


# ── 3. L'écart depuis la veille au soir ────────────────────────────────────


async def test_delta_between_the_two_runs_is_right(db_session, make_spot) -> None:
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    delta = await forecast_delta(db_session, spot, SLOT, now=NOW)

    assert delta.available
    assert delta.run_ts == RUN_MORNING
    assert delta.previous_run_ts == RUN_EVENING
    assert delta.changes["wave_height_m"] == pytest.approx(0.6)
    assert delta.changes["wave_period_s"] == pytest.approx(3.0)


async def test_delta_wraps_directions_the_short_way(db_session, make_spot) -> None:
    """350° → 10°, c'est +20° de rotation, pas −340°."""
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    delta = await forecast_delta(db_session, spot, SLOT, now=NOW)

    assert delta.changes["wave_direction_deg"] == pytest.approx(20.0)


def test_signed_angle_delta_edges() -> None:
    assert signed_angle_delta(10.0, 350.0) == pytest.approx(20.0)
    assert signed_angle_delta(350.0, 10.0) == pytest.approx(-20.0)
    assert signed_angle_delta(95.0, 90.0) == pytest.approx(5.0)


async def test_delta_ignores_runs_emitted_after_yesterday_evening(
    db_session, make_spot
) -> None:
    """Le point de comparaison est hier 20 h locale, pas la passe d'il y a trois heures."""
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    # Une passe de cette nuit, à 3 h : plus récente que « hier soir », elle ne
    # doit pas devenir la référence.
    await upsert_forecast_rows(
        db_session,
        spot.id,
        bundle(wave_height_m=1.5),
        run_ts=datetime(2026, 9, 13, 3, 0, tzinfo=UTC),
    )

    delta = await forecast_delta(db_session, spot, SLOT, now=NOW)

    assert delta.previous_run_ts == RUN_EVENING
    assert delta.changes["wave_height_m"] == pytest.approx(0.6)


async def test_delta_is_empty_with_a_single_run(db_session, make_spot) -> None:
    """Premier jour d'ingestion : rien à comparer, et surtout pas une ligne à elle-même."""
    spot = await make_spot()
    await upsert_forecast_rows(
        db_session, spot.id, bundle(), run_ts=RUN_MORNING
    )

    delta = await forecast_delta(db_session, spot, SLOT, now=NOW)

    assert not delta.available
    assert delta.changes == {}
    assert delta.run_ts == RUN_MORNING


async def test_delta_on_an_unknown_slot_is_empty(db_session, make_spot) -> None:
    spot = await make_spot()
    await _write_two_runs(db_session, spot)

    delta = await forecast_delta(
        db_session, spot, SLOT + timedelta(days=9), now=NOW
    )

    assert not delta.available
    assert delta.run_ts is None


def test_previous_evening_cutoff_is_local_not_utc() -> None:
    """En heure d'été, 20 h à Paris vaut 18 h UTC : se tromper décale d'un run."""
    cutoff = previous_evening_cutoff(NOW, "Europe/Paris")

    assert cutoff == datetime(2026, 9, 12, 18, 0, tzinfo=UTC)


def test_previous_evening_cutoff_stays_on_yesterday_after_dark() -> None:
    """À 23 h, « hier soir » reste hier : le soir d'aujourd'hui n'est pas la référence."""
    late = datetime(2026, 9, 13, 21, 30, tzinfo=UTC)  # 23 h 30 à Paris

    assert previous_evening_cutoff(late, "Europe/Paris") == datetime(
        2026, 9, 12, 18, 0, tzinfo=UTC
    )
