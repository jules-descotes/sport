"""Sans clé, CANDHIS s'éteint proprement — et rien d'autre ne bouge.

C'est l'état dans lequel la production a tourné pendant les trois pushes du lot
1 bis, donc **l'état par défaut du service**. Il mérite d'être tenu par des
tests, pas seulement constaté une fois dans un journal.

La règle tient en trois points : aucun appel ne part, le job n'est pas déclaré,
et le reste de l'application ne s'aperçoit de rien.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.enums import SpotSource, SpotTier
from app.models.forecast import Observation
from app.models.observation_station import ObservationStation
from app.models.profile import Profile
from app.models.spot import Spot
from app.services import scheduler as scheduler_module
from app.services.observations import ingest_home_observations
from app.services.quota import used_today

ANGLET = (43.53217, -1.61500)
GRAVIERE = (43.6640, -1.4400)


async def seed_home(db, user) -> Spot:
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
        observation_station_code="06402",
        observation_station_distance_m=20_400.0,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)

    profile = (
        await db.execute(select(Profile).where(Profile.user_id == user.id))
    ).scalar_one()
    profile.home_spot_id = spot.id
    await db.commit()
    return spot


async def test_the_pass_does_nothing_without_a_key(
    db_session, user, monkeypatch
) -> None:
    """Tout est en place — favori, bouée à 20 km — sauf la clé."""
    monkeypatch.setattr(
        "app.services.observations.settings.candhis_api_key", "", raising=False
    )
    await seed_home(db_session, user)

    assert await ingest_home_observations(db_session) == 0
    # Ni mesure écrite, ni appel compté : le refus est en amont du réseau.
    assert (await db_session.execute(select(Observation))).scalars().all() == []
    assert await used_today(db_session, "candhis") == 0


async def test_the_pass_says_so_when_there_is_no_favourite(
    db_session, user, monkeypatch
) -> None:
    """Pas de favori principal : rien à ingérer, et ce n'est pas une panne."""
    monkeypatch.setattr(
        "app.services.observations.settings.candhis_api_key", "jeton", raising=False
    )
    assert await ingest_home_observations(db_session) == 0


async def test_the_pass_says_so_when_no_buoy_is_close_enough(
    db_session, user, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.services.observations.settings.candhis_api_key", "jeton", raising=False
    )
    # Un favori, mais aucune station en base : rien à 30 km.
    spot = Spot(
        slug="uluwatu",
        name="Uluwatu",
        lat=-8.8149,
        lon=115.0880,
        source=SpotSource.USER.value,
        tier=SpotTier.HOME.value,
        is_active=True,
    )
    db_session.add(spot)
    await db_session.commit()
    await db_session.refresh(spot)
    profile = (
        await db_session.execute(select(Profile).where(Profile.user_id == user.id))
    ).scalar_one()
    profile.home_spot_id = spot.id
    await db_session.commit()

    assert await ingest_home_observations(db_session) == 0


def test_the_scheduler_does_not_declare_the_job_without_a_key(monkeypatch) -> None:
    """Un job inerte qui tourne toutes les heures pollue les journaux.

    Vingt-quatre lignes par jour qui n'apprennent rien finissent par cacher
    celles qui comptent. On ne le déclare donc pas du tout.
    """
    declared: list[str] = []

    class FakeScheduler:
        def add_job(self, *_args, id: str = "", **_kwargs) -> None:
            declared.append(id)

        def start(self) -> None:
            return None

        def shutdown(self, wait: bool = False) -> None:
            return None

    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    monkeypatch.setattr(
        scheduler_module, "AsyncIOScheduler", lambda *a, **k: FakeScheduler()
    )
    monkeypatch.setattr(scheduler_module.settings, "candhis_api_key", "")

    scheduler_module.start_scheduler()
    scheduler_module.stop_scheduler()

    assert "forecast_ingest" in declared
    assert "trash_purge" in declared
    assert "observation_ingest" not in declared


def test_the_scheduler_declares_the_job_once_the_key_is_there(monkeypatch) -> None:
    declared: list[str] = []

    class FakeScheduler:
        def add_job(self, *_args, id: str = "", **_kwargs) -> None:
            declared.append(id)

        def start(self) -> None:
            return None

        def shutdown(self, wait: bool = False) -> None:
            return None

    monkeypatch.setattr(scheduler_module, "_scheduler", None)
    monkeypatch.setattr(
        scheduler_module, "AsyncIOScheduler", lambda *a, **k: FakeScheduler()
    )
    monkeypatch.setattr(scheduler_module.settings, "candhis_api_key", "un-jeton")

    scheduler_module.start_scheduler()
    scheduler_module.stop_scheduler()

    assert "observation_ingest" in declared


def test_the_startup_log_says_which_state_it_is_in(monkeypatch, caplog) -> None:
    """Une fonctionnalité éteinte doit le dire à l'allumage.

    Sinon elle se manifeste trois semaines plus tard par un écran vide que
    personne ne sait expliquer.
    """
    from app.main import log_candhis_state

    monkeypatch.setattr(
        "app.main.settings.candhis_api_key", "", raising=False
    )
    with caplog.at_level("INFO"):
        log_candhis_state()
    assert "CANDHIS inactif" in caplog.text

    caplog.clear()
    monkeypatch.setattr(
        "app.main.settings.candhis_api_key", "un-jeton", raising=False
    )
    with caplog.at_level("INFO"):
        log_candhis_state()
    assert "CANDHIS actif" in caplog.text
    # Le fuseau est journalisé avec : c'est la première ligne à relire le jour
    # où une mesure tombe à côté de la prévision (il n'est pas documenté).
    assert "UTC" in caplog.text


async def test_the_rest_of_the_app_does_not_notice(auth_client, monkeypatch) -> None:
    """Sans clé, les écrans répondent comme avant.

    Le bloc « Maintenant » est simplement absent de la réponse.
    """
    monkeypatch.setattr(
        "app.services.observations.settings.candhis_api_key", "", raising=False
    )
    response = await auth_client.get("/api/v1/calibration")
    assert response.status_code == 200
    assert response.json()["pairs"] == 0
