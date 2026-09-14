"""Bouées : rattachement, choix de la station, ingestion idempotente.

Les coordonnées sont les vraies (cf. docs/CANDHIS.md §7) : Anglet à 43,53217 /
−1,61500 et Saint-Jean-de-Luz à 43,40833 / −1,68167. Un test qui se joue sur
des coordonnées inventées ne dirait rien de la règle des 30 km.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import select

from app.models.enums import SpotSource, SpotTier
from app.models.forecast import Observation
from app.models.observation_station import ObservationStation
from app.models.profile import Profile
from app.models.spot import Spot
from app.services.candhis import CandhisClient, parse_envelope
from app.services.observations import (
    home_station,
    ingest_days,
    ingest_station_window,
    latest_observation,
    link_spots_to_stations,
    nearest_station,
    store_measurements,
)

ANGLET = (43.53217, -1.61500)
SAINT_JEAN_DE_LUZ = (43.40833, -1.68167)
CAP_FERRET = (44.65250, -1.44667)

# Plage de la Gravière, Hossegor — le favori de référence des tests.
GRAVIERE = (43.6640, -1.4400)
# Parlementia, Guéthary — plus près de Saint-Jean-de-Luz que d'Anglet.
PARLEMENTIA = (43.4230, -1.6100)
# La Barre, Anglet — à portée des DEUX bouées (7 km et 18 km), ce qui en
# fait le seul point où l'on puisse montrer qu'une bouée muette est écartée
# au profit d'une autre. Depuis la Gravière, Saint-Jean-de-Luz est à 34 km :
# hors de portée, donc rien à départager.
LA_BARRE = (43.5300, -1.5300)

TR_PAYLOAD = {
    "apiVer": "1.00",
    "success": True,
    "message": "Données TR directionnel H13 campagne `06402`",
    "nbLig": 3,
    "entete": [
        "Date",
        "H1/3 (m)",
        "Hmax (m)",
        "TH1/3 (s)",
        "Dir. au pic (°)",
        "Etal. au pic (°)",
        "Temp. mer (°C)",
    ],
    "results": [
        ["2026-09-14 08:00", "1.10", "1.90", "11.60", "290.0", "19.0", "20.4"],
        ["2026-09-14 08:30", "1.20", "2.00", "11.80", "292.0", "18.0", "20.4"],
        ["2026-09-14 09:00", "1.30", "2.10", "12.00", "295.0", "17.0", "20.5"],
    ],
}


def mock_transport(payload, spy: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if spy is not None:
            spy.append(request)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


async def get_profile(db, user) -> Profile:
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    return result.scalar_one()


async def add_station(
    db,
    code: str,
    name: str,
    lat: float,
    lon: float,
    is_active: bool = True,
    houlographe_type: str = "2",
) -> ObservationStation:
    station = ObservationStation(
        code=code,
        name=name,
        lat=lat,
        lon=lon,
        is_active=is_active,
        is_directional=True,
        houlographe_type=houlographe_type,
        data_type="TR directionnel H13",
        source="candhis",
    )
    db.add(station)
    await db.commit()
    await db.refresh(station)
    return station


async def add_spot(db, slug: str, lat: float, lon: float) -> Spot:
    spot = Spot(
        slug=slug,
        name=slug,
        lat=lat,
        lon=lon,
        source=SpotSource.USER.value,
        tier=SpotTier.HOME.value,
        is_active=True,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    return spot


# --- Choix de la station --------------------------------------------------


async def test_the_nearest_station_wins(db_session) -> None:
    await add_station(db_session, "06402", "Anglet", *ANGLET)
    await add_station(db_session, "06403", "Saint-Jean-de-Luz", *SAINT_JEAN_DE_LUZ)

    found = await nearest_station(db_session, *GRAVIERE)
    assert found is not None
    station, distance = found
    # La Gravière est dans les Landes : Anglet est la plus proche.
    assert station.code == "06402"
    assert distance == pytest.approx(20_000, abs=4_000)


async def test_another_spot_gets_another_station(db_session) -> None:
    """La bouée maison se déduit du favori, elle n'est pas écrite en dur."""
    await add_station(db_session, "06402", "Anglet", *ANGLET)
    await add_station(db_session, "06403", "Saint-Jean-de-Luz", *SAINT_JEAN_DE_LUZ)

    found = await nearest_station(db_session, *PARLEMENTIA)
    assert found is not None
    assert found[0].code == "06403"


async def test_beyond_thirty_kilometres_there_is_no_station(db_session) -> None:
    """La règle des 30 km n'est pas une pudeur de précision.

    Le Cap Ferret est à ~130 km de la Gravière. Une houle mesurée là-bas décrit
    une autre mer, et l'étiqueter « conditions du spot » salirait la donnée
    d'apprentissage.
    """
    await add_station(db_session, "03302", "Cap Ferret", *CAP_FERRET)

    assert await nearest_station(db_session, *GRAVIERE) is None


async def test_an_inactive_station_is_not_chosen(db_session) -> None:
    """Une bouée à l'arrêt donnerait un bloc « Maintenant » perpétuellement vide."""
    await add_station(db_session, "06402", "Anglet", *ANGLET, is_active=False)
    await add_station(db_session, "06403", "Saint-Jean-de-Luz", *SAINT_JEAN_DE_LUZ)

    found = await nearest_station(db_session, *LA_BARRE)
    assert found is not None
    # Anglet est à 7 km et Saint-Jean-de-Luz à 18 km, mais Anglet est muette :
    # on prend la vivante, pas la proche.
    assert found[0].code == "06403"


async def test_every_station_being_silent_leaves_nothing(db_session) -> None:
    await add_station(db_session, "06402", "Anglet", *ANGLET, is_active=False)
    assert await nearest_station(db_session, *LA_BARRE) is None


# --- Rattachement ---------------------------------------------------------


async def test_each_spot_gets_its_station_and_its_distance(db_session) -> None:
    await add_station(db_session, "06402", "Anglet", *ANGLET)
    await add_station(db_session, "06403", "Saint-Jean-de-Luz", *SAINT_JEAN_DE_LUZ)
    graviere = await add_spot(db_session, "la-graviere", *GRAVIERE)
    parlementia = await add_spot(db_session, "parlementia", *PARLEMENTIA)
    ferret = await add_spot(db_session, "cap-ferret-plage", *CAP_FERRET)

    changed = await link_spots_to_stations(db_session)
    # Deux : le Cap Ferret n'a jamais eu de station et n'en a toujours pas —
    # une non-modification ne se compte pas comme une modification.
    assert changed == 2

    await db_session.refresh(graviere)
    await db_session.refresh(parlementia)
    await db_session.refresh(ferret)

    assert graviere.observation_station_code == "06402"
    assert graviere.observation_station_distance_m == pytest.approx(20_000, abs=4_000)
    assert parlementia.observation_station_code == "06403"
    # Hors de portée : aucune station, pas la moins mauvaise.
    assert ferret.observation_station_code is None
    assert ferret.observation_station_distance_m is None


async def test_relinking_is_idempotent(db_session) -> None:
    await add_station(db_session, "06402", "Anglet", *ANGLET)
    await add_spot(db_session, "la-graviere", *GRAVIERE)

    assert await link_spots_to_stations(db_session) == 1
    # Deuxième passage : rien n'a changé, donc rien n'est touché.
    assert await link_spots_to_stations(db_session) == 0


async def test_a_station_leaving_the_network_releases_its_spots(db_session) -> None:
    """Une bouée retirée ne doit pas rester affichée sur un spot.

    Sinon l'écran continuerait d'annoncer « bouée d'Anglet, 20 km » devant un
    bloc qui ne se remplira plus jamais.
    """
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    spot = await add_spot(db_session, "la-graviere", *GRAVIERE)
    await link_spots_to_stations(db_session)

    station.is_active = False
    await db_session.commit()

    assert await link_spots_to_stations(db_session) == 1
    await db_session.refresh(spot)
    assert spot.observation_station_code is None


async def test_the_home_station_follows_the_principal_favourite(
    db_session, user
) -> None:
    await add_station(db_session, "06402", "Anglet", *ANGLET)
    await add_station(db_session, "06403", "Saint-Jean-de-Luz", *SAINT_JEAN_DE_LUZ)
    graviere = await add_spot(db_session, "la-graviere", *GRAVIERE)
    parlementia = await add_spot(db_session, "parlementia", *PARLEMENTIA)
    await link_spots_to_stations(db_session)

    profile = await get_profile(db_session, user)
    profile.home_spot_id = graviere.id
    await db_session.commit()
    found = await home_station(db_session)
    assert found is not None and found[0].code == "06402"

    # Changer de favori principal change de bouée, sans redéploiement.
    profile.home_spot_id = parlementia.id
    await db_session.commit()
    found = await home_station(db_session)
    assert found is not None and found[0].code == "06403"


async def test_no_favourite_means_no_home_station(db_session, user) -> None:
    await add_station(db_session, "06402", "Anglet", *ANGLET)
    assert await home_station(db_session) is None


# --- Écriture -------------------------------------------------------------


async def test_measurements_are_written_once(db_session) -> None:
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    measurements = parse_envelope(TR_PAYLOAD).measurements()

    assert await store_measurements(db_session, station, measurements) == 3

    rows = (await db_session.execute(select(Observation))).scalars().all()
    assert len(rows) == 3
    first = min(rows, key=lambda r: r.ts)
    assert first.hm0_m == pytest.approx(1.1)
    assert first.peak_period_s == pytest.approx(11.6)
    assert first.directional_spread_deg == pytest.approx(19.0)
    assert first.station_id == "06402"
    assert first.source == "candhis"
    # Le format est écrit sur la ligne, comme `model_version` sur `forecasts`.
    assert first.format_version == "tr-directionnel-h13"
    # La ligne brute est gardée entière, libellés d'origine compris.
    assert first.raw["H1/3 (m)"] == "1.10"


async def test_replaying_the_same_pass_writes_nothing_new(db_session) -> None:
    """Le conteneur Railway redémarre : rejouer doit être gratuit.

    `ON CONFLICT DO NOTHING` et pas `DO UPDATE` : une mesure est un constat, et
    un constat ne se corrige pas d'une passe à l'autre.
    """
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    measurements = parse_envelope(TR_PAYLOAD).measurements()

    await store_measurements(db_session, station, measurements)
    await store_measurements(db_session, station, measurements)
    await store_measurements(db_session, station, measurements)

    rows = (await db_session.execute(select(Observation))).scalars().all()
    assert len(rows) == 3


async def test_an_all_sentinel_row_is_not_written(db_session) -> None:
    """Une bouée en avarie émet son horodatage et des 999.9999 partout."""
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    payload = {
        **TR_PAYLOAD,
        "results": [
            ["2026-09-14 10:00", "999.9999", "999.9999", "999.9999", "999.9999", "999.9999", "999.9999"],
            ["2026-09-14 10:30", "1.40", "2.20", "12.10", "300.0", "16.0", "20.6"],
        ],
    }
    written = await store_measurements(
        db_session, station, parse_envelope(payload).measurements()
    )
    assert written == 1


async def test_the_station_remembers_its_last_measurement(db_session) -> None:
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    await store_measurements(
        db_session, station, parse_envelope(TR_PAYLOAD).measurements()
    )
    await db_session.refresh(station)

    last = station.last_measured_at
    assert last is not None
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    assert last == datetime(2026, 9, 14, 9, 0, tzinfo=UTC)


# --- La passe ------------------------------------------------------------


def test_the_window_asks_for_one_day_and_two_across_midnight() -> None:
    """L'API a le jour pour granularité : 3 h est un filtre côté client."""
    midday = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    assert ingest_days(midday) == [date(2026, 9, 14)]

    # À 00 h 30, les trois dernières heures débordent sur la veille : la perdre
    # ferait un trou qu'aucune passe ne viendrait combler.
    just_after_midnight = datetime(2026, 9, 14, 0, 30, tzinfo=UTC)
    assert ingest_days(just_after_midnight) == [date(2026, 9, 13), date(2026, 9, 14)]


async def test_a_pass_keeps_only_the_recent_window(db_session) -> None:
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    spy: list[httpx.Request] = []

    async with httpx.AsyncClient(transport=mock_transport(TR_PAYLOAD, spy)) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton")
        written = await ingest_station_window(
            db_session,
            client,
            station,
            [date(2026, 9, 14)],
            since=datetime(2026, 9, 14, 8, 30, tzinfo=UTC),
        )

    # Une seule requête, et seules les lignes à partir de 08 h 30 sont retenues.
    assert len(spy) == 1
    assert written == 2


async def test_a_refusal_is_logged_and_the_pass_returns_zero(db_session) -> None:
    """Une bouée muette ne doit pas faire tomber l'ordonnanceur."""
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    refusal = {
        "apiVer": "1.00",
        "success": False,
        "message": "Pas de données pour la campagne `06402`",
        "nbLig": 0,
        "entete": None,
        "results": None,
    }

    async with httpx.AsyncClient(transport=mock_transport(refusal)) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton")
        written = await ingest_station_window(
            db_session, client, station, [date(2026, 9, 14)]
        )

    assert written == 0


async def test_an_unexpected_format_is_skipped_not_fatal(db_session) -> None:
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    surprise = {"apiVer": "2.00", "donnees": [{"hauteur": 1.2}]}

    async with httpx.AsyncClient(transport=mock_transport(surprise)) as http:
        client = CandhisClient(db_session, client=http, api_key="jeton")
        written = await ingest_station_window(
            db_session, client, station, [date(2026, 9, 14)]
        )

    assert written == 0
    assert (await db_session.execute(select(Observation))).scalars().all() == []


async def test_without_a_key_a_pass_does_nothing(db_session) -> None:
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    spy: list[httpx.Request] = []

    async with httpx.AsyncClient(transport=mock_transport(TR_PAYLOAD, spy)) as http:
        client = CandhisClient(db_session, client=http, api_key="")
        written = await ingest_station_window(
            db_session, client, station, [date(2026, 9, 14)]
        )

    assert written == 0
    assert spy == []


async def test_the_latest_measurement_is_the_most_recent_one(db_session) -> None:
    station = await add_station(db_session, "06402", "Anglet", *ANGLET)
    await store_measurements(
        db_session, station, parse_envelope(TR_PAYLOAD).measurements()
    )

    latest = await latest_observation(db_session, "06402")
    assert latest is not None
    assert latest.ts == datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    assert latest.hm0_m == pytest.approx(1.3)
