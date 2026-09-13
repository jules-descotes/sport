"""Training — semis, objectifs mesurés, proposition du jour, mode séance.

Ce qui se teste ici, dans l'ordre de ce qui décide si l'onglet sera rouvert :

- l'**import d'exercices** sur un extrait fixé, catégories comprises ;
- la **proposition du jour** sur quatre scénarios, dont les trois jours de
  surf d'affilée ;
- la **séance écourtée**, comptée à part et exclue de l'avancement hebdo.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.exercise import Exercise
from app.models.formula import Formula
from app.models.objective import Objective, ObjectiveMeasurement
from app.models.surf_session import SurfSession
from app.models.workout import WorkoutSession
from app.services.training import (
    SURF_STREAK_FOR_RECOVERY,
    ensure_training_seeded,
    objective_progress,
    propose_today,
    seed_exercises,
    seed_formulas,
    seed_objectives,
    surf_streak_days,
    week_bounds,
    weekly_counts,
)
from app.services.training_catalog import EXERCISES, FORMULAS, OBJECTIVES, normalize_name


# ── Semis ──────────────────────────────────────────────────────────────────


async def test_seeding_is_idempotent(db_session, user) -> None:
    """Le catalogue évoluera ; rejouer le semis ne doit rien dupliquer."""
    await ensure_training_seeded(db_session, user.id)
    await ensure_training_seeded(db_session, user.id)

    exercises = (await db_session.execute(select(Exercise))).scalars().all()
    formulas = (await db_session.execute(select(Formula))).scalars().all()
    objectives = (await db_session.execute(select(Objective))).scalars().all()

    assert len(exercises) == len(EXERCISES)
    assert len(formulas) == len(FORMULAS)
    assert len(objectives) == len(OBJECTIVES)


async def test_seeding_never_erases_measurements(db_session, user) -> None:
    """Un semis rejoué ne doit pas effacer six mois de suivi."""
    await ensure_training_seeded(db_session, user.id)
    objective = (
        await db_session.execute(
            select(Objective).where(Objective.slug == "gainage")
        )
    ).scalar_one()
    db_session.add(
        ObjectiveMeasurement(
            objective_id=objective.id, measured_on=date(2026, 9, 1), value=80.0
        )
    )
    await db_session.commit()

    await seed_objectives(db_session, user.id)
    await db_session.refresh(objective)

    assert [m.value for m in objective.measurements] == [80.0]


async def test_every_formula_item_resolves_to_an_exercise(db_session, user) -> None:
    """Une formule qui cite un exercice absent servirait une séance trouée."""
    await seed_exercises(db_session)
    await seed_formulas(db_session)

    formulas = (await db_session.execute(select(Formula))).scalars().all()
    for formula in formulas:
        expected = next(
            entry for entry in FORMULAS if entry["slug"] == formula.slug
        )
        assert len(formula.items) == len(expected["items"]), formula.slug
        for item in formula.items:
            assert item.exercise is not None


async def test_the_five_design_formulas_are_there(db_session, user) -> None:
    """Les cinq du document design, plus au moins deux variantes chacune."""
    await seed_exercises(db_session)
    await seed_formulas(db_session)

    formulas = (await db_session.execute(select(Formula))).scalars().all()
    by_family: dict[str, int] = {}
    for formula in formulas:
        by_family[formula.family] = by_family.get(formula.family, 0) + 1

    for family in (
        "reveil",
        "post-surf",
        "abdos",
        "souplesse-longue",
        "renfo-surf",
    ):
        assert family in by_family, family
        # La principale plus au moins deux variantes.
        assert by_family[family] >= 3, family


async def test_every_formula_states_its_principle(db_session) -> None:
    """C'est ce qui distingue une formule composée d'un programme recopié."""
    await seed_exercises(db_session)
    await seed_formulas(db_session)

    formulas = (await db_session.execute(select(Formula))).scalars().all()
    for formula in formulas:
        assert formula.principle.strip(), formula.slug
        assert len(formula.principle) > 40, formula.slug


async def test_formula_items_never_carry_reps_and_duration_at_once(
    db_session,
) -> None:
    """Un gainage se tient, une rotation se compte. Le mode séance a besoin de
    savoir lequel des deux compter."""
    await seed_exercises(db_session)
    await seed_formulas(db_session)

    formulas = (await db_session.execute(select(Formula))).scalars().all()
    for formula in formulas:
        for item in formula.items:
            assert (item.reps is None) != (
                item.duration_s is None
            ), f"{formula.slug} / {item.position}"


async def test_builtin_exercises_declare_their_licence(db_session) -> None:
    await seed_exercises(db_session)
    exercises = (await db_session.execute(select(Exercise))).scalars().all()
    for exercise in exercises:
        assert exercise.source == "builtin"
        assert exercise.license
        assert exercise.instructions


# ── Import d'exercices, sur un extrait fixé ────────────────────────────────


def test_import_classifies_a_fixed_sample() -> None:
    """L'extrait est figé ici : c'est le seul moyen de voir bouger le
    classement le jour où l'on touche aux mots-clés.

    Le classement est **grossier et on le sait** — trois catégories, parce
    qu'une taxonomie fine se vérifie mal et qu'un import en apporterait une
    fausse. Même prudence que pour `sport=surfing`.
    """
    from scripts.import_exercises import classify

    sample = [
        # (nom, indices de la base d'origine, catégorie attendue)
        ("Plank", ["Abs", "abdominals"], "core"),
        ("3/4 Sit-Up", ["abdominals", "strength"], "core"),
        ("Dumbbell Side Bend", ["abdominals"], "core"),
        ("Standing Hamstring Stretch", ["stretching", "hamstrings"], "mobility"),
        ("Calves-SMR", ["stretching", "calves"], "mobility"),
        ("Thoracic Rotation", ["stretching", "back"], "mobility"),
        # Piège relevé sur l'échantillon wger du 13/09 : « rotation » seul
        # rangeait un renforcement de coiffe dans la mobilité.
        ("Cable External Rotation", ["Shoulders", "shoulders"], "strength"),
        ("Barbell Bench Press", ["Chest", "chest"], "strength"),
        ("Chin Up", ["Biceps", "lats"], "strength"),
        ("Barbell Squat", ["Legs", "quadriceps"], "strength"),
    ]

    for name, hints, expected in sample:
        assert classify(name, hints) == expected, name


def test_import_normalizes_names_for_deduplication() -> None:
    """« Push-Ups » et « push up » sont le même exercice."""
    assert normalize_name("Push-Ups") == normalize_name("push ups")
    assert normalize_name("Élévation latérale") == "elevation laterale"
    assert normalize_name("  3/4 Sit-Up ") == "3 4 sit up"


async def test_import_enriches_instead_of_duplicating(db_session, monkeypatch):
    """L'import rapproche par `aliases` : il complète la ligne rédigée à la
    main au lieu d'en créer une deuxième sous son nom anglais."""
    from scripts import import_exercises

    await seed_exercises(db_session)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _scope():
        yield db_session

    monkeypatch.setattr(import_exercises, "async_session", lambda: _scope())

    incoming = [
        import_exercises.Incoming(
            name="Push Up",
            category="strength",
            muscle_group="chest",
            instructions="English text we do not want.",
            image_url="https://example.org/pushup.jpg",
            source="free-exercise-db",
            license="Public Domain (Unlicense)",
        ),
        import_exercises.Incoming(
            name="Zercher Squat",
            category="strength",
            muscle_group="quadriceps",
            instructions="…",
            image_url=None,
            source="free-exercise-db",
            license="Public Domain (Unlicense)",
        ),
    ]

    report = await import_exercises.apply(incoming)

    assert report.enriched == 1
    assert report.created == 1

    pompes = (
        await db_session.execute(select(Exercise).where(Exercise.slug == "pompes"))
    ).scalar_one()
    assert pompes.image_url == "https://example.org/pushup.jpg"
    # Les consignes françaises sont à nous : l'import n'y touche pas.
    assert "pop-up" in (pompes.instructions or "")
    # La licence de l'image suit l'image.
    assert "Unlicense" in (pompes.license or "")


# ── Objectifs ──────────────────────────────────────────────────────────────


async def test_start_value_is_the_first_measurement(db_session, user) -> None:
    """Un départ tapé au clavier est une estimation qu'on prendra ensuite pour
    une mesure. Il n'y en a pas."""
    await ensure_training_seeded(db_session, user.id)
    objective = (
        await db_session.execute(
            select(Objective).where(Objective.slug == "assouplissement")
        )
    ).scalar_one()

    assert objective.start_value is None

    for day, value in ((date(2026, 8, 1), -14.0), (date(2026, 9, 1), -6.0)):
        db_session.add(
            ObjectiveMeasurement(
                objective_id=objective.id, measured_on=day, value=value
            )
        )
    await db_session.commit()
    await db_session.refresh(objective)

    assert objective.start_value == -14.0
    assert objective.current_value == -6.0


async def test_progress_reads_in_the_direction_of_the_objective(
    db_session, user
) -> None:
    """« Mains-sol » va de −14 cm vers 0 : c'est un progrès, pas un recul."""
    await ensure_training_seeded(db_session, user.id)
    objective = (
        await db_session.execute(
            select(Objective).where(Objective.slug == "assouplissement")
        )
    ).scalar_one()

    for day, value in ((date(2026, 8, 1), -14.0), (date(2026, 9, 1), -7.0)):
        db_session.add(
            ObjectiveMeasurement(
                objective_id=objective.id, measured_on=day, value=value
            )
        )
    await db_session.commit()
    await db_session.refresh(objective)

    progress = objective_progress(objective, date(2026, 9, 2))
    assert progress.ratio == pytest.approx(0.5)


async def test_measurement_reminder_fires_after_the_frequency(
    db_session, user
) -> None:
    await ensure_training_seeded(db_session, user.id)
    objective = (
        await db_session.execute(
            select(Objective).where(Objective.slug == "gainage")
        )
    ).scalar_one()

    # Aucune mesure : c'est d'abord de mesurer que l'objectif a besoin.
    assert objective_progress(objective, date(2026, 9, 13)).needs_measurement

    db_session.add(
        ObjectiveMeasurement(
            objective_id=objective.id, measured_on=date(2026, 9, 10), value=90.0
        )
    )
    await db_session.commit()
    await db_session.refresh(objective)

    assert not objective_progress(objective, date(2026, 9, 13)).needs_measurement
    assert objective_progress(objective, date(2026, 10, 5)).needs_measurement


async def test_measuring_twice_the_same_day_replaces(auth_client, db_session, user):
    """Deux chiffres pour la même chose le même jour ne veulent rien dire."""
    await ensure_training_seeded(db_session, user.id)
    objective = (
        await db_session.execute(
            select(Objective).where(Objective.slug == "gainage")
        )
    ).scalar_one()

    for value in (80.0, 95.0):
        response = await auth_client.post(
            f"/api/v1/training/objectives/{objective.id}/measurements",
            json={"value": value, "measured_on": "2026-09-12"},
        )
        assert response.status_code == 201

    body = response.json()
    assert len(body["measurements"]) == 1
    assert body["measurements"][0]["value"] == 95.0


# ── Proposition du jour, quatre scénarios ─────────────────────────────────


async def _measure(db_session, user_id: int, slug: str, values) -> None:
    objective = (
        await db_session.execute(
            select(Objective)
            .where(Objective.user_id == user_id)
            .where(Objective.slug == slug)
        )
    ).scalar_one()
    for day, value in values:
        db_session.add(
            ObjectiveMeasurement(
                objective_id=objective.id, measured_on=day, value=value
            )
        )
    await db_session.commit()


async def _surf_on(db_session, user, spot, days_ago: int) -> None:
    db_session.add(
        SurfSession(
            user_id=user.id,
            spot_id=spot.id,
            started_at=datetime.now(UTC).replace(hour=9) - timedelta(days=days_ago),
            duration_min=90,
            discipline="surf",
            status="rated",
            # Demi-points entiers en base : 8 se lit 4,0 (cf. migration 0010).
            rating_conditions_half=8,
            rating_personal_half=8,
        )
    )
    await db_session.commit()


async def test_scenario_one_nothing_measured_proposes_a_measured_objective(
    db_session, user
):
    """Scénario 1 — page blanche. Aucun objectif mesuré : la proposition doit
    exister quand même, et servir un objectif."""
    await ensure_training_seeded(db_session, user.id)

    proposal = await propose_today(db_session, user.id, date(2026, 9, 14))

    assert proposal.formula is not None
    assert proposal.formula.objective_slugs
    assert "mesure" in proposal.reason or "retard" in proposal.reason


async def test_scenario_two_serves_the_objective_most_behind(db_session, user):
    """Scénario 2 — la souplesse est presque acquise, le gainage non : c'est
    le gainage qui décide."""
    await ensure_training_seeded(db_session, user.id)
    today = date(2026, 9, 14)

    # Assouplissement : −14 → −1 sur une cible à 0, soit 93 % du chemin.
    await _measure(
        db_session,
        user.id,
        "assouplissement",
        ((date(2026, 6, 1), -14.0), (date(2026, 9, 13), -1.0)),
    )
    # Mobilité : 24° → 43° sur une cible à 45°, presque acquise aussi.
    await _measure(
        db_session,
        user.id,
        "mobilite-thoracique",
        ((date(2026, 6, 1), 24.0), (date(2026, 9, 13), 43.0)),
    )
    # Gainage : 80 s → 85 s sur une cible à 180 s. Le plus en retard, de loin.
    await _measure(
        db_session,
        user.id,
        "gainage",
        ((date(2026, 6, 1), 80.0), (date(2026, 9, 13), 85.0)),
    )

    proposal = await propose_today(db_session, user.id, today)

    assert proposal.formula is not None
    assert "gainage" in (proposal.formula.objective_slugs or [])
    assert "Gainage" in proposal.reason


async def test_scenario_three_three_surf_days_rules_out_strength(
    db_session, user, make_spot
):
    """Scénario 3 — trois jours de surf d'affilée. Post-surf ou Réveil, jamais
    Renfo : le corps a déjà eu sa dose."""
    await ensure_training_seeded(db_session, user.id)
    spot = await make_spot()

    today = datetime.now(UTC).date()
    for days_ago in range(SURF_STREAK_FOR_RECOVERY):
        await _surf_on(db_session, user, spot, days_ago)

    streak = await surf_streak_days(db_session, user.id, today)
    assert streak >= SURF_STREAK_FOR_RECOVERY

    proposal = await propose_today(db_session, user.id, today)

    assert proposal.formula is not None
    tags = set(proposal.formula.tags or [])
    assert "strength" not in tags
    assert tags & {"post_surf", "morning"}
    assert "surf d'affilée" in proposal.reason


async def test_scenario_four_weekly_target_met_steps_aside(
    db_session, user, make_spot
):
    """Scénario 4 — les abdos sont à 3/3 cette semaine. Ils ne passent plus
    devant une formule qui n'a pas été faite."""
    await ensure_training_seeded(db_session, user.id)
    today = datetime.now(UTC).date()

    await _measure(
        db_session,
        user.id,
        "gainage",
        ((today - timedelta(days=60), 80.0), (today - timedelta(days=1), 85.0)),
    )

    start, _ = week_bounds(today)
    for index in range(3):
        db_session.add(
            WorkoutSession(
                user_id=user.id,
                formula_name="Abdos",
                formula_family="abdos",
                started_at=start + timedelta(days=index, hours=8),
                ended_at=start + timedelta(days=index, hours=8, minutes=15),
                completed=True,
                cut_short=False,
                feeling=4,
            )
        )
    await db_session.commit()

    done = await weekly_counts(db_session, user.id, today)
    assert done.get("abdos") == 3

    proposal = await propose_today(db_session, user.id, today)
    assert proposal.formula is not None
    assert proposal.formula.family != "abdos"


async def test_alternatives_are_one_per_family(db_session, user):
    """Remplacer en un tap doit proposer autre chose, pas une variante de la
    même séance."""
    await ensure_training_seeded(db_session, user.id)

    proposal = await propose_today(db_session, user.id, date(2026, 9, 14))
    families = [formula.family for formula in proposal.alternatives]

    assert len(families) == len(set(families))
    assert proposal.formula is not None
    assert proposal.formula.family not in families


# ── Mode séance ────────────────────────────────────────────────────────────


async def _start_workout(auth_client, db_session, slug: str) -> dict:
    formula = (
        await db_session.execute(select(Formula).where(Formula.slug == slug))
    ).scalar_one()
    response = await auth_client.post(
        "/api/v1/training/workouts", json={"formula_id": formula.id}
    )
    assert response.status_code == 201
    return response.json()


async def test_a_finished_session_is_complete(auth_client, db_session, user):
    await ensure_training_seeded(db_session, user.id)
    workout = await _start_workout(auth_client, db_session, "reveil")

    formula = (
        await db_session.execute(select(Formula).where(Formula.slug == "reveil"))
    ).scalar_one()
    sets = [
        {
            "position": index,
            "formula_item_id": item.id,
            "exercise_id": item.exercise_id,
            "exercise_name": item.exercise.name,
            "reps": item.reps,
            "duration_s": item.duration_s,
            "skipped": False,
        }
        for index, item in enumerate(formula.items)
        for _ in range(item.sets)
    ]

    response = await auth_client.post(
        f"/api/v1/training/workouts/{workout['id']}/finish",
        json={"feeling": 4, "sets": sets},
    )

    body = response.json()
    assert body["completed"] is True
    assert body["cut_short"] is False
    assert body["feeling"] == 4


async def test_a_session_cut_short_is_counted_apart(auth_client, db_session, user):
    """Le point qui fait que ces lignes valent quelque chose.

    Une séance de 28 minutes arrêtée à la sixième est un renseignement — la
    formule est trop longue, ou mal placée. La compter comme faite effacerait
    exactement l'information qui permettrait de la corriger.
    """
    await ensure_training_seeded(db_session, user.id)
    workout = await _start_workout(auth_client, db_session, "renfo-surf")

    formula = (
        await db_session.execute(
            select(Formula).where(Formula.slug == "renfo-surf")
        )
    ).scalar_one()
    # Deux séries faites sur les vingt et quelques prévues.
    first = formula.items[0]
    sets = [
        {
            "position": index,
            "formula_item_id": first.id,
            "exercise_id": first.exercise_id,
            "exercise_name": first.exercise.name,
            "reps": first.reps,
            "duration_s": first.duration_s,
            "skipped": False,
        }
        for index in range(2)
    ]

    response = await auth_client.post(
        f"/api/v1/training/workouts/{workout['id']}/finish",
        json={"feeling": 2, "sets": sets},
    )

    body = response.json()
    assert body["cut_short"] is True
    assert body["completed"] is False


async def test_a_session_cut_short_does_not_fill_the_weekly_target(
    auth_client, db_session, user
):
    """Sinon « 3 / 3 » pourrait vouloir dire trois abandons à la deuxième
    minute."""
    await ensure_training_seeded(db_session, user.id)
    workout = await _start_workout(auth_client, db_session, "abdos")

    await auth_client.post(
        f"/api/v1/training/workouts/{workout['id']}/finish",
        json={"feeling": 2, "sets": []},
    )

    done = await weekly_counts(db_session, user.id, datetime.now(UTC).date())
    assert done.get("abdos", 0) == 0


async def test_skipping_an_exercise_is_recorded_as_such(
    auth_client, db_session, user
):
    """« Je suis passé au suivant » n'est pas « je ne suis jamais arrivé
    jusque-là » : l'une dit qu'un exercice ne passe pas, l'autre que la séance
    était trop longue."""
    await ensure_training_seeded(db_session, user.id)
    workout = await _start_workout(auth_client, db_session, "reveil")

    response = await auth_client.post(
        f"/api/v1/training/workouts/{workout['id']}/finish",
        json={
            "feeling": 3,
            "sets": [
                {
                    "position": 0,
                    "exercise_name": "Chat-vache",
                    "reps": 10,
                    "skipped": False,
                },
                {
                    "position": 1,
                    "exercise_name": "Rotation thoracique",
                    "reps": None,
                    "skipped": True,
                },
            ],
        },
    )

    body = response.json()
    assert [entry["skipped"] for entry in body["sets"]] == [False, True]


async def test_finishing_twice_is_refused(auth_client, db_session, user):
    await ensure_training_seeded(db_session, user.id)
    workout = await _start_workout(auth_client, db_session, "reveil")

    await auth_client.post(
        f"/api/v1/training/workouts/{workout['id']}/finish", json={"sets": []}
    )
    second = await auth_client.post(
        f"/api/v1/training/workouts/{workout['id']}/finish", json={"sets": []}
    )

    assert second.status_code == 409


async def test_the_formula_name_is_frozen_on_the_workout(
    auth_client, db_session, user
):
    """Une formule renommée plus tard ne doit pas réécrire l'historique."""
    await ensure_training_seeded(db_session, user.id)
    workout = await _start_workout(auth_client, db_session, "post-surf")

    stored = await db_session.get(WorkoutSession, workout["id"])
    assert stored.formula_name == "Post-surf"
    assert stored.formula_family == "post-surf"


# ── Écran ──────────────────────────────────────────────────────────────────


async def test_overview_serves_the_whole_screen_in_one_call(auth_client):
    response = await auth_client.get("/api/v1/training/overview")

    assert response.status_code == 200
    body = response.json()
    assert len(body["objectives"]) == len(OBJECTIVES)
    assert len(body["formulas"]) == len(FORMULAS)
    assert body["proposal"]["formula"] is not None
    assert body["proposal"]["reason"]


async def test_overview_route_is_declared_before_any_identifier(auth_client):
    """Sans cet ordre, FastAPI lirait « overview » comme un identifiant."""
    assert (await auth_client.get("/api/v1/training/overview")).status_code == 200


async def test_exercise_library_is_searchable(auth_client):
    await auth_client.get("/api/v1/training/overview")

    response = await auth_client.get(
        "/api/v1/training/exercises", params={"category": "core"}
    )

    body = response.json()
    assert body
    assert all(item["category"] == "core" for item in body)
    assert all(item["source"] for item in body)


async def test_training_requires_authentication(client):
    assert (await client.get("/api/v1/training/overview")).status_code == 401
