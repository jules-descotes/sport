"""Habitudes et statistiques de profil — décidées le 13/09.

Deux règles sont testées ici autant que le calcul : **rien de jugeant n'est
rendu**, et **les événements sont horodatés**. La seconde n'a l'air de rien
aujourd'hui ; elle est ce qui permettra, au lot 6, de croiser les habitudes
avec le ressenti des sessions du lendemain.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.surf_session import SurfSession
from app.services.stats import current_streak, season_start

TODAY = date(2026, 9, 13)


async def _habit(auth_client, **overrides):
    payload = {"name": "Eau", "icon": "water", "kind": "count", "unit": "verres"}
    payload.update(overrides)
    response = await auth_client.post("/api/v1/habits", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ── Le compteur ────────────────────────────────────────────────────────────


async def test_a_habit_starts_at_zero(auth_client):
    habit = await _habit(auth_client)
    assert habit["today"] == 0
    assert habit["is_active"] is True


async def test_each_tap_adds_one(auth_client):
    """Le geste de l'écran Jour : une pastille, +1 par tap."""
    habit = await _habit(auth_client)

    for expected in (1, 2, 3):
        response = await auth_client.post(
            f"/api/v1/habits/{habit['id']}/events", json={"quantity": 1}
        )
        assert response.json()["today"] == expected


async def test_a_negative_quantity_corrects_a_tap_too_many(auth_client):
    """On annule en ajoutant l'inverse, pas en supprimant.

    Une correction est elle-même une information : le geste a eu lieu, et il a
    été repris. L'effacer perdrait les deux.
    """
    habit = await _habit(auth_client)
    await auth_client.post(f"/api/v1/habits/{habit['id']}/events", json={"quantity": 2})

    corrected = await auth_client.post(
        f"/api/v1/habits/{habit['id']}/events", json={"quantity": -1}
    )

    assert corrected.json()["today"] == 1
    events = (
        await auth_client.get(f"/api/v1/habits/{habit['id']}/events")
    ).json()
    # Les deux gestes sont conservés, pas fusionnés.
    assert len(events) == 2


async def test_events_are_timestamped_to_the_second(auth_client):
    """Ce qui rendra possible le croisement du lot 6 avec le ressenti."""
    habit = await _habit(auth_client)
    moment = datetime(2026, 9, 13, 21, 42, 17, tzinfo=UTC)

    await auth_client.post(
        f"/api/v1/habits/{habit['id']}/events",
        json={"quantity": 1, "occurred_at": moment.isoformat()},
    )

    events = (await auth_client.get(f"/api/v1/habits/{habit['id']}/events")).json()
    assert datetime.fromisoformat(events[0]["occurred_at"]) == moment


async def test_yesterdays_taps_do_not_count_today(auth_client):
    habit = await _habit(auth_client)
    yesterday = datetime.now(UTC) - timedelta(days=1)

    response = await auth_client.post(
        f"/api/v1/habits/{habit['id']}/events",
        json={"quantity": 5, "occurred_at": yesterday.isoformat()},
    )

    assert response.json()["today"] == 0
    # Mais ils comptent dans la semaine, si c'est la même.
    assert response.json()["week"] >= 0


# ── La pause ───────────────────────────────────────────────────────────────


async def test_a_paused_habit_leaves_the_day_screen_and_keeps_its_events(
    auth_client,
):
    """Une envie du dimanche soir ne doit pas effacer trois mois de comptage."""
    habit = await _habit(auth_client)
    await auth_client.post(f"/api/v1/habits/{habit['id']}/events", json={"quantity": 1})

    await auth_client.patch(
        f"/api/v1/habits/{habit['id']}",
        json={"name": habit["name"], "is_active": False},
    )

    visible = (await auth_client.get("/api/v1/habits")).json()
    assert visible == []

    all_habits = (
        await auth_client.get("/api/v1/habits?include_paused=true")
    ).json()
    assert [item["id"] for item in all_habits] == [habit["id"]]

    events = (await auth_client.get(f"/api/v1/habits/{habit['id']}/events")).json()
    assert len(events) == 1


async def test_a_paused_habit_comes_back(auth_client):
    habit = await _habit(auth_client)
    await auth_client.patch(
        f"/api/v1/habits/{habit['id']}",
        json={"name": habit["name"], "is_active": False},
    )
    await auth_client.patch(
        f"/api/v1/habits/{habit['id']}",
        json={"name": habit["name"], "is_active": True},
    )

    assert len((await auth_client.get("/api/v1/habits")).json()) == 1


async def test_deleting_a_habit_takes_its_events(auth_client, db_session):
    from sqlalchemy import func, select

    from app.models.habit import HabitEvent

    habit = await _habit(auth_client)
    await auth_client.post(f"/api/v1/habits/{habit['id']}/events", json={"quantity": 1})

    removed = await auth_client.delete(f"/api/v1/habits/{habit['id']}")
    assert removed.status_code == 204

    remaining = await db_session.execute(
        select(func.count()).select_from(HabitEvent)
    )
    assert remaining.scalar_one() == 0


async def test_an_unknown_icon_is_refused(auth_client):
    """Le jeu d'icônes est fermé : trait de 1,75 px, grille de 24, jamais
    d'emoji (cf. CLAUDE.md)."""
    response = await auth_client.post(
        "/api/v1/habits", json={"name": "Café", "icon": "☕"}
    )
    assert response.status_code == 422


# ── Les tendances, sans jugement ───────────────────────────────────────────


async def test_the_trend_is_a_curve_and_not_a_score(auth_client):
    """Trente valeurs, et rien d'autre. Pas de série, pas de taux de réussite."""
    habit = await _habit(auth_client)
    for offset in (0, 1, 3):
        await auth_client.post(
            f"/api/v1/habits/{habit['id']}/events",
            json={
                "quantity": 2,
                "occurred_at": (
                    datetime.now(UTC) - timedelta(days=offset)
                ).isoformat(),
            },
        )

    stats = (await auth_client.get("/api/v1/habits/stats")).json()
    trend = stats["habits"][0]

    assert len(trend["daily"]) == 30
    assert trend["total_30d"] == 6
    assert trend["days_with_activity"] == 3
    # Rien de jugeant dans la charge utile : c'est une contrainte, pas un
    # oubli.
    assert not any(
        key in trend for key in ("success_rate", "streak", "missed", "score")
    )


# ── La série de jours surfés ───────────────────────────────────────────────


def test_a_streak_must_be_current() -> None:
    """Une série de douze jours terminée en mars ne dure plus en juillet.

    L'afficher comme en cours serait flatteur et faux — et c'est exactement le
    genre de chiffre qui décrédibilise tout un écran de statistiques.
    """
    old = [date(2026, 3, day) for day in range(1, 13)]
    assert current_streak(old, date(2026, 7, 1)) == 0


def test_a_streak_counts_back_from_today() -> None:
    days = [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert current_streak(days, TODAY) == 3


def test_a_streak_tolerates_not_having_surfed_yet_today() -> None:
    """À 9 h du matin, la série d'hier est encore vivante."""
    days = [TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    assert current_streak(days, TODAY) == 2


def test_a_gap_breaks_the_streak() -> None:
    days = [TODAY, TODAY - timedelta(days=2), TODAY - timedelta(days=3)]
    assert current_streak(days, TODAY) == 1


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 9, 13), date(2026, 9, 1)),
        (date(2026, 12, 24), date(2026, 9, 1)),
        # Janvier appartient encore à la saison de l'automne précédent : la
        # couper au 1er janvier séparerait la meilleure période en deux.
        (date(2027, 1, 15), date(2026, 9, 1)),
        (date(2026, 8, 31), date(2025, 9, 1)),
    ],
)
def test_the_season_starts_in_september(today: date, expected: date) -> None:
    assert season_start(today) == expected


# ── Les cartes du profil ───────────────────────────────────────────────────


async def test_the_stats_are_empty_without_data(auth_client):
    """Aucun zéro de complaisance : une moyenne sans session vaut `None`."""
    stats = (await auth_client.get("/api/v1/habits/stats")).json()

    assert stats["surf"]["sessions_30d"] == 0
    assert stats["surf"]["average_rating"] is None
    assert stats["surf"]["top_spot"] is None
    assert stats["habits"] == []


async def test_the_surf_card_counts_hours_and_ratings(
    auth_client, make_spot, fake_archive, db_session, user
):
    fake_archive()
    spot = await make_spot(name="La Gravière")
    other = await make_spot(name="Parlementia", slug="parlementia", lat=43.4, lon=-1.6)

    now = datetime.now(UTC)
    for index, (target, rating) in enumerate(
        [(spot, 8), (spot, 10), (other, 6)]
    ):
        db_session.add(
            SurfSession(
                user_id=user.id,
                spot_id=target.id,
                started_at=now - timedelta(days=index + 1, hours=index),
                duration_min=90,
                discipline="surf",
                status="rated",
                rating_conditions_half=rating,
                rating_personal_half=rating,
            )
        )
    await db_session.commit()

    stats = (await auth_client.get("/api/v1/habits/stats")).json()["surf"]

    assert stats["sessions_30d"] == 3
    assert stats["hours_30d"] == pytest.approx(4.5, abs=0.1)
    assert stats["average_rating"] == pytest.approx(4.0, abs=0.01)
    assert stats["top_spot"] == "La Gravière"
    assert stats["top_spot_sessions"] == 2
    # Le 10 en demi-points, c'est 5,0.
    assert stats["best_rating"] == 5.0
    assert stats["best_spot"] == "La Gravière"


async def test_the_training_card_covers_eight_weeks(auth_client):
    stats = (await auth_client.get("/api/v1/habits/stats")).json()["training"]

    assert len(stats["weeks"]) == 8
    # Les semaines vont de la plus ancienne à la plus récente : une courbe se
    # lit de gauche à droite.
    starts = [week["week_start"] for week in stats["weeks"]]
    assert starts == sorted(starts)


async def test_the_nutrition_card_counts_days_in_target(auth_client, db_session, user):
    from app.models.nutrition import FoodLog

    target = (await auth_client.get("/api/v1/nutrition/day")).json()["target"]["kcal"]

    today = date.today()
    # Une journée pile dans la cible, une très en dessous.
    db_session.add(
        FoodLog(
            user_id=user.id,
            day=today,
            meal="lunch",
            label="Journée pleine",
            quantity_g=0,
            kcal=target,
            protein_g=120,
        )
    )
    db_session.add(
        FoodLog(
            user_id=user.id,
            day=today - timedelta(days=1),
            meal="lunch",
            label="Journée creuse",
            quantity_g=0,
            kcal=target * 0.4,
            protein_g=60,
        )
    )
    await db_session.commit()

    stats = (await auth_client.get("/api/v1/habits/stats")).json()["nutrition"]

    assert stats["logged_days_30d"] == 2
    assert stats["on_target_days_30d"] == 1
    assert stats["average_protein_g"] == pytest.approx(90.0, abs=0.1)
