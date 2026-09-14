"""Calibration prévision ↔ mesure : paires, biais par délai, bloc « Maintenant ».

Les données sont **semées** — on choisit un biais connu et on vérifie qu'on le
retrouve, signe compris. Un test de calibration qui se contenterait de compter
des lignes ne dirait rien du seul piège réel : le sens du biais.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.calibration import ForecastVsObserved
from app.models.enums import SpotSource, SpotTier
from app.models.forecast import Forecast, Observation
from app.models.observation_station import ObservationStation
from app.models.spot import Spot
from app.services.calibration import (
    LEAD_BUCKETS,
    MIN_PAIRS,
    bucket_for,
    build_pairs,
    calibration,
    sentence,
)
from app.services.observations import buoy_now

ANGLET = (43.53217, -1.61500)
GRAVIERE = (43.6640, -1.4400)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


async def seed_spot_and_station(db) -> tuple[Spot, ObservationStation]:
    station = ObservationStation(
        code="06402",
        name="Anglet",
        lat=ANGLET[0],
        lon=ANGLET[1],
        is_active=True,
        is_directional=True,
        houlographe_type="2",
        source="candhis",
    )
    spot = Spot(
        slug="la-graviere",
        name="La Gravière",
        lat=GRAVIERE[0],
        lon=GRAVIERE[1],
        source=SpotSource.USER.value,
        tier=SpotTier.HOME.value,
        is_active=True,
        observation_station_code="06402",
        observation_station_distance_m=20_400.0,
    )
    db.add_all([station, spot])
    await db.commit()
    await db.refresh(station)
    await db.refresh(spot)
    return spot, station


def add_forecast(db, spot: Spot, ts: datetime, run_ts: datetime, height: float,
                 period: float = 10.0) -> None:
    db.add(
        Forecast(
            spot_id=spot.id,
            ts=ts,
            run_ts=run_ts,
            source="open-meteo",
            model="meteofrance_wave",
            model_version="mfwam-2025",
            wave_height_m=height,
            wave_peak_period_s=period,
            fetched_at=run_ts,
        )
    )


def add_observation(db, ts: datetime, height: float, period: float = 10.0) -> None:
    db.add(
        Observation(
            station_id="06402",
            ts=ts,
            source="candhis",
            hm0_m=height,
            peak_period_s=period,
            format_version="tr-directionnel-h13",
            fetched_at=ts,
        )
    )


# --- Les tranches ---------------------------------------------------------


@pytest.mark.parametrize(
    "lead, expected",
    [
        (0.0, "0-6h"),
        (5.9, "0-6h"),
        (6.0, "6-24h"),
        (23.9, "6-24h"),
        (24.0, "24-48h"),
        (48.0, "48h+"),
        (140.0, "48h+"),
    ],
)
def test_lead_buckets_have_no_gap_and_no_overlap(lead: float, expected: str) -> None:
    assert bucket_for(lead) == expected


def test_a_negative_lead_belongs_to_no_bucket() -> None:
    """Un run postérieur à l'heure cible n'est pas une prévision."""
    assert bucket_for(-1.0) is None


# --- Appariement ----------------------------------------------------------


async def test_one_measured_hour_pairs_with_every_run_that_announced_it(
    db_session,
) -> None:
    """C'est tout l'objet de l'historisation des runs du lot 1 ter."""
    spot, station = await seed_spot_and_station(db_session)
    target = NOW

    # Trois runs pour la même heure : trois jours avant, la veille, le matin.
    for lead in (72, 24, 3):
        add_forecast(db_session, spot, target, target - timedelta(hours=lead), 1.0)
    add_observation(db_session, target, 1.2)
    await db_session.commit()

    written = await build_pairs(
        db_session, spot, "06402", target - timedelta(hours=1), target + timedelta(hours=1)
    )
    assert written == 3

    rows = (await db_session.execute(select(ForecastVsObserved))).scalars().all()
    assert sorted(round(row.lead_hours) for row in rows) == [3, 24, 72]
    # Toutes portent la même mesure : c'est la même heure.
    assert {row.observed_hm0_m for row in rows} == {1.2}


async def test_a_run_after_the_target_hour_is_refused(db_session) -> None:
    """Le décalage train/serve dans sa version la plus discrète.

    Une prévision émise après coup est un constat. La compter flatterait le
    modèle exactement là où on cherche à le mesurer.
    """
    spot, station = await seed_spot_and_station(db_session)
    target = NOW

    add_forecast(db_session, spot, target, target + timedelta(hours=2), 1.0)
    add_observation(db_session, target, 1.2)
    await db_session.commit()

    assert await build_pairs(
        db_session, spot, "06402", target - timedelta(hours=1), target + timedelta(hours=1)
    ) == 0


async def test_half_hourly_measurements_snap_to_the_nearest_whole_hour(
    db_session,
) -> None:
    """Les mesures sont demi-horaires, les prévisions horaires.

    On garde la mesure la plus proche du top de l'heure plutôt que d'interpoler
    une précision qui n'existe pas dans la prévision d'en face.
    """
    spot, station = await seed_spot_and_station(db_session)
    target = NOW

    add_forecast(db_session, spot, target, target - timedelta(hours=6), 1.0)
    # 12 h 00 et 12 h 30 : c'est celle de 12 h 00 qui doit gagner.
    add_observation(db_session, target, 1.2)
    add_observation(db_session, target + timedelta(minutes=30), 2.5)
    await db_session.commit()

    await build_pairs(
        db_session, spot, "06402", target - timedelta(hours=1), target + timedelta(hours=1)
    )
    row = (await db_session.execute(select(ForecastVsObserved))).scalar_one()
    assert row.observed_hm0_m == pytest.approx(1.2)


async def test_replaying_the_pairing_writes_nothing_new(db_session) -> None:
    spot, station = await seed_spot_and_station(db_session)
    target = NOW
    add_forecast(db_session, spot, target, target - timedelta(hours=6), 1.0)
    add_observation(db_session, target, 1.2)
    await db_session.commit()

    window = (target - timedelta(hours=1), target + timedelta(hours=1))
    await build_pairs(db_session, spot, "06402", *window)
    await build_pairs(db_session, spot, "06402", *window)

    rows = (await db_session.execute(select(ForecastVsObserved))).scalars().all()
    assert len(rows) == 1


# --- Biais ----------------------------------------------------------------


async def test_the_bias_is_signed_the_way_the_sentence_reads(db_session) -> None:
    """Le seul vrai piège : le sens.

    On sème un modèle qui **annonce 1,0 m là où la bouée en mesure 1,2** —
    c'est-à-dire un modèle qui sous-estime. Le biais doit être **positif**, et
    la phrase doit dire « sous-estime ». Un signe inversé ici ferait lire tout
    l'écran à l'envers, sans que rien ne plante jamais.
    """
    spot, station = await seed_spot_and_station(db_session)

    for index in range(MIN_PAIRS + 4):
        ts = NOW - timedelta(hours=index)
        add_forecast(db_session, spot, ts, ts - timedelta(hours=3), 1.0)
        add_observation(db_session, ts, 1.2)
    await db_session.commit()

    await build_pairs(
        db_session, spot, "06402", NOW - timedelta(days=2), NOW + timedelta(hours=1)
    )

    result = await calibration(db_session, "06402", now=NOW + timedelta(minutes=1))
    bucket = next(b for b in result.hm0 if b.bucket == "0-6h")

    assert bucket.pairs >= MIN_PAIRS
    assert bucket.bias == pytest.approx(0.2, abs=0.001)
    assert bucket.mae == pytest.approx(0.2, abs=0.001)
    # 0,2 / 1,2 ≈ 16,7 %
    assert bucket.bias_pct == pytest.approx(16.7, abs=0.2)

    phrase = sentence(bucket, "la hauteur")
    assert phrase is not None and "sous-estime" in phrase


async def test_a_model_that_announces_too_much_overestimates(db_session) -> None:
    spot, station = await seed_spot_and_station(db_session)

    for index in range(MIN_PAIRS + 4):
        ts = NOW - timedelta(hours=index)
        add_forecast(db_session, spot, ts, ts - timedelta(hours=3), 1.5)
        add_observation(db_session, ts, 1.0)
    await db_session.commit()

    await build_pairs(
        db_session, spot, "06402", NOW - timedelta(days=2), NOW + timedelta(hours=1)
    )
    result = await calibration(db_session, "06402", now=NOW + timedelta(minutes=1))
    bucket = next(b for b in result.hm0 if b.bucket == "0-6h")

    assert bucket.bias == pytest.approx(-0.5, abs=0.001)
    phrase = sentence(bucket, "la hauteur")
    assert phrase is not None and "surestime" in phrase


async def test_too_few_pairs_gives_a_count_and_no_figure(db_session) -> None:
    """Un biais sur huit mesures est du bruit affiché avec une décimale."""
    spot, station = await seed_spot_and_station(db_session)

    for index in range(3):
        ts = NOW - timedelta(hours=index)
        add_forecast(db_session, spot, ts, ts - timedelta(hours=3), 1.0)
        add_observation(db_session, ts, 1.2)
    await db_session.commit()

    await build_pairs(
        db_session, spot, "06402", NOW - timedelta(days=2), NOW + timedelta(hours=1)
    )
    result = await calibration(db_session, "06402", now=NOW + timedelta(minutes=1))
    bucket = next(b for b in result.hm0 if b.bucket == "0-6h")

    assert bucket.pairs == 3
    assert bucket.bias is None
    assert sentence(bucket) is None


async def test_pairs_outside_the_window_are_ignored(db_session) -> None:
    """Trente jours **glissants** : un biais de modèle change avec la saison."""
    spot, station = await seed_spot_and_station(db_session)

    old = NOW - timedelta(days=60)
    for index in range(MIN_PAIRS + 4):
        ts = old - timedelta(hours=index)
        add_forecast(db_session, spot, ts, ts - timedelta(hours=3), 1.0)
        add_observation(db_session, ts, 1.2)
    await db_session.commit()

    await build_pairs(
        db_session, spot, "06402", old - timedelta(days=2), old + timedelta(hours=1)
    )
    result = await calibration(db_session, "06402", now=NOW)
    assert result.pairs == 0


async def test_a_model_that_is_right_says_so_without_a_verb(db_session) -> None:
    spot, station = await seed_spot_and_station(db_session)

    for index in range(MIN_PAIRS + 4):
        ts = NOW - timedelta(hours=index)
        add_forecast(db_session, spot, ts, ts - timedelta(hours=3), 1.20)
        add_observation(db_session, ts, 1.21)
    await db_session.commit()

    await build_pairs(
        db_session, spot, "06402", NOW - timedelta(days=2), NOW + timedelta(hours=1)
    )
    result = await calibration(db_session, "06402", now=NOW + timedelta(minutes=1))
    bucket = next(b for b in result.hm0 if b.bucket == "0-6h")

    phrase = sentence(bucket, "la hauteur")
    assert phrase is not None and "tombe juste" in phrase


# --- Le bloc « Maintenant » -----------------------------------------------


async def test_now_shows_the_measurement_against_its_own_hour(db_session) -> None:
    """Comparer 9 h 30 mesuré à 11 h prévu ne mesurerait que le temps qui passe."""
    spot, station = await seed_spot_and_station(db_session)

    measured_at = NOW - timedelta(minutes=20)
    hour = measured_at.replace(minute=0, second=0, microsecond=0)
    add_forecast(db_session, spot, hour, hour - timedelta(hours=3), 1.4, period=11.0)
    # Une prévision pour une **autre** heure, qui ne doit pas être retenue.
    add_forecast(
        db_session, spot, hour + timedelta(hours=2), hour, 2.9, period=15.0
    )
    add_observation(db_session, measured_at, 1.2, period=11.5)
    await db_session.commit()

    payload = await buoy_now(db_session, spot, at=NOW)
    assert payload is not None
    assert payload["hm0_m"] == pytest.approx(1.2)
    assert payload["forecast_hm0_m"] == pytest.approx(1.4)
    assert payload["hm0_delta_m"] == pytest.approx(-0.2, abs=0.001)
    assert payload["station_name"] == "Anglet"
    assert payload["distance_m"] == pytest.approx(20_400.0)
    assert payload["age_minutes"] == 20
    assert payload["sentence"] == "prévu 1,4 m, mesuré 1,2 m"


async def test_a_measurement_older_than_three_hours_hides_the_block(
    db_session,
) -> None:
    """Un bloc « Maintenant » qui montre la houle de ce matin est trompeur."""
    spot, station = await seed_spot_and_station(db_session)
    add_observation(db_session, NOW - timedelta(hours=4), 1.2)
    await db_session.commit()

    assert await buoy_now(db_session, spot, at=NOW) is None


async def test_a_spot_without_a_station_has_no_block(db_session) -> None:
    spot, station = await seed_spot_and_station(db_session)
    spot.observation_station_code = None
    await db_session.commit()

    assert await buoy_now(db_session, spot, at=NOW) is None


async def test_the_block_survives_a_missing_forecast(db_session) -> None:
    """Un spot qu'on vient d'ouvrir n'a pas encore de prévision en base.

    La mesure reste affichable : elle ne dépend pas du modèle.
    """
    spot, station = await seed_spot_and_station(db_session)
    add_observation(db_session, NOW - timedelta(minutes=10), 1.2)
    await db_session.commit()

    payload = await buoy_now(db_session, spot, at=NOW)
    assert payload is not None
    assert payload["hm0_m"] == pytest.approx(1.2)
    assert payload["forecast_hm0_m"] is None
    assert payload["sentence"] is None


# --- L'API ----------------------------------------------------------------


async def test_the_endpoint_answers_empty_before_any_measurement(
    auth_client, db_session
) -> None:
    """Un état normal, pas une erreur.

    La carte dit « pas encore assez de mesures » ; elle n'affiche pas un zéro,
    qui se lirait comme un modèle parfait.
    """
    response = await auth_client.get("/api/v1/calibration")
    assert response.status_code == 200

    payload = response.json()
    assert payload["pairs"] == 0
    assert payload["sentences"] == []
    # Les quatre tranches sont rendues quand même : l'écran a une forme stable.
    assert [bucket["bucket"] for bucket in payload["hm0"]] == [
        label for label, _, _ in LEAD_BUCKETS
    ]
    assert all(bucket["bias"] is None for bucket in payload["hm0"])


async def test_the_endpoint_serves_the_bias_and_its_sentence(
    auth_client, db_session
) -> None:
    spot, station = await seed_spot_and_station(db_session)

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for index in range(MIN_PAIRS + 4):
        ts = now - timedelta(hours=index)
        add_forecast(db_session, spot, ts, ts - timedelta(hours=3), 1.0)
        add_observation(db_session, ts, 1.2)
    await db_session.commit()
    await build_pairs(
        db_session, spot, "06402", now - timedelta(days=2), now + timedelta(hours=1)
    )

    response = await auth_client.get("/api/v1/calibration?station=06402")
    assert response.status_code == 200

    payload = response.json()
    assert payload["station_id"] == "06402"
    bucket = next(b for b in payload["hm0"] if b["bucket"] == "0-6h")
    assert bucket["bias"] == pytest.approx(0.2, abs=0.001)
    assert any("sous-estime" in phrase for phrase in payload["sentences"])


async def test_the_endpoint_needs_a_session(client) -> None:
    assert (await client.get("/api/v1/calibration")).status_code == 401
