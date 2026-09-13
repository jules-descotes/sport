"""Seuils personnels de qualité — décidés le 13/09 (retours n° 4).

Huit nombres qui disent où commence le bon. Ils font **deux** choses, et c'est
l'essentiel de ce que ces tests protègent : ils teintent les cellules du
tableau horaire et ils calculent la note. Un seul jeu pour les deux — deux jeux
finiraient par montrer une cellule « bonne » sous une note de 2, et personne ne
saurait lequel croire.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.scoring import Conditions, Thresholds, score_conditions

ONSHORE_WEST = 270.0
TS = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def conditions(**kwargs) -> Conditions:
    base = dict(
        wave_height_m=1.4,
        wave_period_s=12.0,
        wave_direction_deg=285.0,
        wind_speed_kt=8.0,
        wind_direction_deg=90.0,
        tide_position=0.5,
        tide_trend_m_per_h=0.3,
    )
    base.update(kwargs)
    return Conditions(ts=TS, **base)


# ── L'API ──────────────────────────────────────────────────────────────────


async def test_the_first_read_creates_the_row_at_jules_defaults(
    auth_client,
) -> None:
    """Pas de semis en migration : la ligne naît à la première lecture.

    Et les défauts sont ceux que Jules a donnés, pas des « valeurs
    raisonnables » trouvées ailleurs — c'est la seule raison pour laquelle ils
    ont le droit d'être des défauts.
    """
    response = await auth_client.get("/api/v1/auth/me/thresholds")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["period_good_s"] == 8.0
    assert body["period_great_s"] == 12.0
    assert body["wind_top_kt"] == 10.0
    assert body["wind_strong_kt"] == 15.0
    assert body["wind_very_strong_kt"] == 20.0
    assert body["wave_min_m"] == 1.2
    assert body["wave_good_m"] == 1.8
    assert body["wave_big_m"] == 2.5


async def test_reading_twice_does_not_make_two_rows(auth_client, db_session) -> None:
    from sqlalchemy import func, select

    from app.models.thresholds import UserThresholds

    await auth_client.get("/api/v1/auth/me/thresholds")
    await auth_client.get("/api/v1/auth/me/thresholds")

    count = await db_session.execute(
        select(func.count()).select_from(UserThresholds)
    )
    assert count.scalar_one() == 1


async def test_one_knob_moves_without_touching_the_others(auth_client) -> None:
    """On règle un curseur, pas les huit.

    Exiger les huit obligerait l'écran à toutes les connaître pour en changer
    une, et une valeur oubliée retomberait au défaut sans prévenir.
    """
    await auth_client.get("/api/v1/auth/me/thresholds")

    response = await auth_client.put(
        "/api/v1/auth/me/thresholds", json={"wave_min_m": 0.9}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["wave_min_m"] == 0.9
    assert body["wave_good_m"] == 1.8
    assert body["period_good_s"] == 8.0


async def test_a_partial_update_is_checked_against_what_is_stored(
    auth_client,
) -> None:
    """L'ordre est vérifié **après** fusion, sinon la règle ne dit rien.

    Un envoi qui ne porte que « très bon » doit être confronté au « bon » déjà
    en base — le valider seul laisserait passer une rampe repliée.
    """
    await auth_client.put(
        "/api/v1/auth/me/thresholds", json={"period_good_s": 11}
    )

    response = await auth_client.put(
        "/api/v1/auth/me/thresholds", json={"period_great_s": 10}
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"wind_top_kt": 18, "wind_strong_kt": 15},
        {"wave_min_m": 2.0, "wave_good_m": 1.5},
        {"period_good_s": 13, "period_great_s": 12},
    ],
)
async def test_crossed_thresholds_are_refused_not_reordered(
    auth_client, payload
) -> None:
    """Refusé plutôt que remis dans l'ordre en silence.

    Intervertir « bon » et « très bon » se corrige d'un tap si on le dit, et se
    paie en couleurs incompréhensibles pendant des semaines si on ne le dit pas.
    """
    response = await auth_client.put("/api/v1/auth/me/thresholds", json=payload)

    assert response.status_code == 422


async def test_an_absurd_value_is_refused(auth_client) -> None:
    """Une période de quarante secondes n'est pas une préférence."""
    response = await auth_client.put(
        "/api/v1/auth/me/thresholds", json={"period_good_s": 40}
    )

    assert response.status_code == 422


async def test_the_change_survives_a_reread(auth_client) -> None:
    await auth_client.put(
        "/api/v1/auth/me/thresholds",
        json={"wave_min_m": 0.8, "wave_good_m": 1.2, "wave_big_m": 1.8},
    )

    body = (await auth_client.get("/api/v1/auth/me/thresholds")).json()

    assert body["wave_min_m"] == 0.8
    assert body["wave_big_m"] == 1.8


async def test_thresholds_need_a_session(client) -> None:
    assert (await client.get("/api/v1/auth/me/thresholds")).status_code == 401


# ── Le score les lit ───────────────────────────────────────────────────────


def test_the_defaults_are_the_curves_of_lot_1_for_the_period() -> None:
    """On a changé la **source** des nombres, pas la forme du jugement."""
    assert Thresholds().period_curve() == (
        (4.0, 0.05),
        (6.0, 0.20),
        (8.0, 0.45),
        (11.0, 0.85),
        (14.0, 1.00),
        (20.0, 1.00),
    )


def test_a_higher_period_bar_lowers_the_same_slot() -> None:
    """Quelqu'un qui n'aime que les longues périodes note 10 s plus bas."""
    demanding = Thresholds(period_good_s=11, period_great_s=15)

    default = score_conditions(conditions(wave_period_s=10.0), ONSHORE_WEST)
    strict = score_conditions(
        conditions(wave_period_s=10.0), ONSHORE_WEST, thresholds=demanding
    )

    assert strict.value < default.value


def test_a_lower_swell_bar_raises_a_small_day() -> None:
    small_is_fine = Thresholds(wave_min_m=0.6, wave_good_m=1.0, wave_big_m=1.5)

    default = score_conditions(conditions(wave_height_m=0.9), ONSHORE_WEST)
    lenient = score_conditions(
        conditions(wave_height_m=0.9), ONSHORE_WEST, thresholds=small_is_fine
    )

    assert lenient.value > default.value


def test_the_wind_bar_decides_when_direction_starts_to_matter() -> None:
    """`wind_very_strong_kt` est le vent au-delà duquel la direction fait tout.

    Le posant plus bas, un onshore de quinze nœuds pèse déjà de tout son poids ;
    le posant haut, il est encore à moitié pardonné.
    """
    onshore = conditions(wind_speed_kt=15.0, wind_direction_deg=270.0)

    tolerant = score_conditions(
        onshore, ONSHORE_WEST, thresholds=Thresholds(wind_very_strong_kt=35)
    )
    touchy = score_conditions(
        onshore, ONSHORE_WEST, thresholds=Thresholds(wind_very_strong_kt=16)
    )

    assert touchy.value < tolerant.value


def test_a_wind_bar_under_the_glassy_mark_does_not_fold_the_ramp() -> None:
    """Garde-fou : un seuil absurde ne doit pas rendre une note absurde."""
    score = score_conditions(
        conditions(wind_speed_kt=12.0, wind_direction_deg=270.0),
        ONSHORE_WEST,
        thresholds=Thresholds(
            wind_top_kt=1.5, wind_strong_kt=2.0, wind_very_strong_kt=3.0
        ),
    )

    assert 1.0 <= score.value <= 5.0


# ── Elles voyagent avec la prévision ───────────────────────────────────────


async def test_the_forecast_carries_the_thresholds(
    auth_client, make_spot, make_forecast
) -> None:
    """Servies **avec** la prévision, pas dans un second appel.

    Le tableau teinte ses cellules avec les nombres qui ont calculé les notes,
    et c'est une requête de moins à l'ouverture de l'écran — sur un réseau de
    parking de plage, c'est la différence entre un écran et une attente.
    """
    spot = await make_spot()
    await make_forecast(spot)
    await auth_client.put(
        "/api/v1/auth/me/thresholds", json={"period_good_s": 9.5}
    )

    body = (
        await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")
    ).json()

    assert body["thresholds"] is not None
    assert body["thresholds"]["period_good_s"] == 9.5
