"""`--since` / `--until` : la fenêtre du backfill, sur réponses mockées.

Ce qui est éprouvé ici, c'est **ce qui part sur le réseau** : les dates
demandées à CANDHIS, et le nombre d'appels. Un backfill qui se trompe de
fenêtre ne se voit pas à l'écran — il se voit des semaines plus tard, comme un
trou dans l'historique que plus rien ne vient combler.
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
from app.services import candhis as candhis_module
from scripts import backfill_candhis

ANGLET = (43.53217, -1.61500)
GRAVIERE = (43.6640, -1.4400)

TR_PAYLOAD = {
    "apiVer": "1.00",
    "success": True,
    "message": "Données TR directionnel H13 campagne `06402`",
    "nbLig": 1,
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
    ],
}

AUCUNE_DONNEE = {
    "apiVer": "1.00",
    "success": False,
    "message": "Pas de données pour la campagne `06402` du 2026-09-01 au 2026-09-02",
    "nbLig": 0,
    "entete": None,
    "results": None,
}


@pytest.fixture
def home(db_session, user):
    """Un favori principal, et une bouée à 20 km de lui."""

    async def _seed() -> Spot:
        db_session.add(
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
        db_session.add(spot)
        await db_session.commit()
        await db_session.refresh(spot)

        profile = (
            await db_session.execute(
                select(Profile).where(Profile.user_id == user.id)
            )
        ).scalar_one()
        profile.home_spot_id = spot.id
        await db_session.commit()
        return spot

    return _seed


@pytest.fixture
def run_backfill(db_session, monkeypatch):
    """Lance `backfill_candhis.run` avec un transport mocké, et espionne."""

    def _install(payload=TR_PAYLOAD):
        spy: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            spy.append(request)
            return httpx.Response(200, json=payload)

        class Session:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, *exc_info):
                return None

        monkeypatch.setattr(backfill_candhis, "async_session", lambda: Session())
        monkeypatch.setattr(
            candhis_module.settings, "candhis_api_key", "un-jeton"
        )

        transport = httpx.MockTransport(handler)

        async def enter(self):
            self._client = httpx.AsyncClient(transport=transport)
            self._owns_client = True
            return self

        monkeypatch.setattr(candhis_module.CandhisClient, "__aenter__", enter)
        return spy

    return _install


def ranges(spy: list[httpx.Request]) -> list[tuple[str, str]]:
    return [
        (request.url.params["dateDeb"], request.url.params["dateFin"])
        for request in spy
    ]


async def test_since_and_until_bound_the_window(home, run_backfill) -> None:
    """La fenêtre demandée est celle qu'on a écrite, à un jour de rab près.

    Le jour de plus sur `dateFin` est volontaire : la documentation ne dit pas
    si elle est incluse (cf. docs/CANDHIS.md §4.6).
    """
    await home()
    spy = run_backfill()

    assert (
        await backfill_candhis.run(
            since=date(2026, 9, 1), until=date(2026, 9, 10)
        )
        == 0
    )

    assert ranges(spy) == [("2026-09-01", "2026-09-11")]


async def test_a_long_window_is_cut_into_twelve_month_slices(
    home, run_backfill
) -> None:
    await home()
    spy = run_backfill()

    await backfill_candhis.run(since=date(2024, 1, 1), until=date(2026, 9, 14))

    asked = ranges(spy)
    assert len(asked) == 3
    # Première tranche à partir de la date demandée, dernière jusqu'à --until
    # (plus le jour de sécurité).
    assert asked[0][0] == "2024-01-01"
    assert asked[-1][1] == "2026-09-15"
    # Aucun trou entre deux tranches : chaque début suit la fin de la
    # précédente — c'est ce que garantit `day_chunks`.
    for (_, previous_end), (next_start, _) in zip(asked, asked[1:]):
        assert next_start == previous_end


async def test_until_defaults_to_today(home, run_backfill) -> None:
    await home()
    spy = run_backfill()

    await backfill_candhis.run(since=date(2026, 9, 1))

    today = datetime.now(UTC).date()
    assert ranges(spy)[-1][1] == (today + candhis_module.ONE_DAY).isoformat()


async def test_a_future_until_is_brought_back_to_today(home, run_backfill) -> None:
    """La bouée n'a pas de mesures au futur : les demander gaspille du quota."""
    await home()
    spy = run_backfill()

    await backfill_candhis.run(
        since=date(2026, 9, 1), until=date(2030, 1, 1)
    )

    today = datetime.now(UTC).date()
    assert ranges(spy)[-1][1] == (today + candhis_module.ONE_DAY).isoformat()


async def test_an_inverted_window_refuses_without_calling(
    home, run_backfill
) -> None:
    await home()
    spy = run_backfill()

    code = await backfill_candhis.run(
        since=date(2026, 9, 10), until=date(2026, 9, 1)
    )

    assert code == 1
    assert spy == []


async def test_dry_run_shows_the_window_without_calling(home, run_backfill) -> None:
    await home()
    spy = run_backfill()

    assert (
        await backfill_candhis.run(
            since=date(2026, 9, 1), until=date(2026, 9, 10), dry_run=True
        )
        == 0
    )
    assert spy == []


async def test_a_no_data_answer_is_logged_raw_and_does_not_stop_the_run(
    home, run_backfill, caplog, db_session
) -> None:
    """Le cas qui a motivé ce correctif : lire ce que le serveur dit vraiment.

    La passe continue — « pas de données sur cette tranche » est une réponse,
    pas une panne — et le corps brut part dans les journaux en INFO.
    """
    await home()
    spy = run_backfill(payload=AUCUNE_DONNEE)

    with caplog.at_level("INFO"):
        code = await backfill_candhis.run(
            since=date(2026, 9, 1), until=date(2026, 9, 2)
        )

    assert code == 0
    assert len(spy) == 1
    assert "réponse brute" in caplog.text
    assert "Pas de données pour la campagne" in caplog.text
    # Rien écrit, et rien cassé.
    assert (await db_session.execute(select(Observation))).scalars().all() == []
