"""Le volet `observed` d'une session préfère la bouée à l'archive.

La règle en une phrase : **une mesure bat une sortie de modèle, mais seulement
là où elle mesure vraiment.** La bouée ne connaît ni le vent ni la marée ; le
volet garde donc l'archive pour tout le reste.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import SpotSource, SpotTier
from app.models.forecast import Observation
from app.models.observation_station import ObservationStation
from app.models.spot import Spot
from app.services.backfill import build_conditions_snapshot, window_timestamps

ANGLET = (43.53217, -1.61500)
GRAVIERE = (43.6640, -1.4400)

STARTED_AT = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)


async def seed(db, *, linked: bool = True) -> Spot:
    db.add(
        ObservationStation(
            code="06402",
            name="Anglet",
            lat=ANGLET[0],
            lon=ANGLET[1],
            is_active=True,
            is_directional=True,
            houlographe_type="2",
            source="candhis",
        )
    )
    spot = Spot(
        slug="la-graviere",
        name="La Gravière",
        lat=GRAVIERE[0],
        lon=GRAVIERE[1],
        source=SpotSource.USER.value,
        tier=SpotTier.HOME.value,
        is_active=True,
        onshore_dir_deg=270.0,
        observation_station_code="06402" if linked else None,
        observation_station_distance_m=20_400.0 if linked else None,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


async def add_measurements(db, timestamps, height: float = 1.85) -> None:
    for ts in timestamps:
        db.add(
            Observation(
                station_id="06402",
                ts=ts,
                source="candhis",
                hm0_m=height,
                peak_period_s=13.5,
                wave_direction_deg=300.0,
                water_temperature_c=19.5,
                format_version="tr-directionnel-h13",
                fetched_at=ts,
            )
        )
    await db.commit()


async def test_the_buoy_overrides_the_archive_on_the_swell(
    db_session, fake_archive, archive_bundle
) -> None:
    """La houle passe à la mesure ; le vent reste celui de l'archive.

    C'est la nuance qui porte tout : une bouée ne mesure pas le vent, et
    reconstruire le volet à partir d'elle seule perdrait la moitié de ce qui
    décide d'une session.
    """
    fake_archive(archive_bundle(STARTED_AT))
    spot = await seed(db_session)
    timestamps = window_timestamps(STARTED_AT)
    await add_measurements(db_session, timestamps)

    snapshot = await build_conditions_snapshot(db_session, spot, STARTED_AT)
    observed = snapshot["observed"]
    assert observed

    for entry in observed:
        assert entry["wave_source"] == "buoy"
        assert entry["wave_height_m"] == pytest.approx(1.85)
        assert entry["wave_peak_period_s"] == pytest.approx(13.5)
        # Le vent survit : il vient de l'archive, la bouée n'en a pas.
        assert entry["wind_speed_kt"] is not None


async def test_the_station_and_its_distance_are_stored(db_session, fake_archive, archive_bundle) -> None:
    """« bouée d'Anglet, 20 km » doit être lisible sans rouvrir le catalogue."""
    fake_archive(archive_bundle(STARTED_AT))
    spot = await seed(db_session)
    timestamps = window_timestamps(STARTED_AT)
    await add_measurements(db_session, timestamps)

    snapshot = await build_conditions_snapshot(db_session, spot, STARTED_AT)
    station = snapshot["observed_station"]

    assert station["code"] == "06402"
    assert station["name"] == "Anglet"
    assert station["source"] == "candhis"
    assert station["distance_m"] == pytest.approx(20_400.0)
    assert station["hours"] == len(timestamps)


async def test_without_measurements_the_archive_stands_alone(
    db_session, fake_archive, archive_bundle
) -> None:
    """Une session à l'étranger, une bouée en panne : le volet reste complet."""
    fake_archive(archive_bundle(STARTED_AT))
    spot = await seed(db_session)

    snapshot = await build_conditions_snapshot(db_session, spot, STARTED_AT)
    observed = snapshot["observed"]

    assert observed
    assert all(entry["wave_source"] == "model" for entry in observed)
    assert "observed_station" not in snapshot


async def test_a_spot_without_a_station_never_looks_for_one(
    db_session, fake_archive, archive_bundle
) -> None:
    fake_archive(archive_bundle(STARTED_AT))
    spot = await seed(db_session, linked=False)
    await add_measurements(db_session, window_timestamps(STARTED_AT))

    snapshot = await build_conditions_snapshot(db_session, spot, STARTED_AT)
    assert all(entry["wave_source"] == "model" for entry in snapshot["observed"])
    assert "observed_station" not in snapshot


async def test_a_partial_window_mixes_and_says_which_is_which(
    db_session, fake_archive, archive_bundle
) -> None:
    """La bouée s'est tue une heure. Chaque ligne dit d'où elle vient.

    Sans ce marquage, l'historique mélangerait des mesures et des sorties de
    modèle sous la même étiquette « observé », et plus personne — y compris le
    modèle du lot 6 — ne pourrait les départager.
    """
    fake_archive(archive_bundle(STARTED_AT))
    spot = await seed(db_session)
    timestamps = window_timestamps(STARTED_AT)
    # Seulement la première et la dernière heure sont mesurées.
    await add_measurements(db_session, [timestamps[0], timestamps[-1]])

    snapshot = await build_conditions_snapshot(db_session, spot, STARTED_AT)
    sources = [entry["wave_source"] for entry in snapshot["observed"]]

    assert sources == ["buoy", "model", "buoy"]
    assert snapshot["observed_station"]["hours"] == 2


async def test_a_measurement_half_an_hour_off_still_counts(
    db_session, fake_archive, archive_bundle
) -> None:
    """Les mesures sont demi-horaires : exiger l'heure pleine n'en garderait aucune."""
    fake_archive(archive_bundle(STARTED_AT))
    spot = await seed(db_session)
    timestamps = window_timestamps(STARTED_AT)
    await add_measurements(
        db_session, [ts + timedelta(minutes=28) for ts in timestamps]
    )

    snapshot = await build_conditions_snapshot(db_session, spot, STARTED_AT)
    assert all(entry["wave_source"] == "buoy" for entry in snapshot["observed"])


async def test_a_measurement_two_hours_off_does_not_count(
    db_session, fake_archive, archive_bundle
) -> None:
    """Au-delà de la demi-heure, il n'y a pas de mesure pour cette heure-là.

    Rapprocher une mesure de 8 h d'une heure de 10 h, ce n'est plus arrondir,
    c'est inventer.
    """
    fake_archive(archive_bundle(STARTED_AT))
    spot = await seed(db_session)
    timestamps = window_timestamps(STARTED_AT)
    # Une seule mesure, à 05 h, alors que la fenêtre court de 08 h à 10 h. Un
    # décalage appliqué à toute la série ne prouverait rien : elle retomberait
    # sur les heures de la fenêtre par translation.
    await add_measurements(db_session, [timestamps[0] - timedelta(hours=3)])

    snapshot = await build_conditions_snapshot(db_session, spot, STARTED_AT)
    assert all(entry["wave_source"] == "model" for entry in snapshot["observed"])
    assert "observed_station" not in snapshot
