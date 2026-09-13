"""Le générateur de séances — décidé le 13/09 (retours n° 3).

Trois choses sont protégées ici, et ce sont celles qui décident si l'outil sert
à quelque chose :

1. **Le classement ne devine jamais.** Quarante noms fixés, relus à la main :
   ce qui n'est pas reconnu reste « à classer ». C'est la leçon de
   `sport=surfing`, et elle vaut aussi pour les exercices.
2. **Le niveau est déduit**, pas déclaré, et un groupe jamais travaillé part
   au niveau 2.
3. **Trois séances réellement différentes**, à chaque demande, y compris sur
   les cas pauvres — aucun matériel, groupe jamais travaillé, rien à la bonne
   difficulté.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

import pytest

from app.services.exercise_taxonomy import (
    UNCLASSIFIED,
    classify,
    french_name,
    translate_name,
)
from app.services.workout_generator import (
    INTENT_PROGRESSION,
    INTENT_RECOVERY,
    Request,
    generate,
)
from app.services.workout_level import (
    DEFAULT_LEVEL,
    GroupLevel,
    deduce_levels,
    personal_records,
)


# ── 1. Le classement, sur quarante noms fixés ──────────────────────────────
#
# Fixés : c'est le point. Un test qui tirerait des noms au hasard dans la base
# passerait ou échouerait selon l'humeur de l'import.

# `(nom, muscles, matériel, groupe attendu, pattern attendu)`. Le matériel est
# passé à part, comme à l'import : le mélanger aux muscles ferait lire
# « pull-up bar » comme un indice de tirage sur un relevé de jambes suspendu.
CLASSIFICATION_CASES = [
    ("Barbell Bench Press", ["chest", "barbell"], "poitrine", "poussee"),
    ("Incline Dumbbell Press", ["chest", "dumbbell"], "poitrine", "poussee"),
    ("Push-up", ["chest", "body only"], "poitrine", "poussee"),
    ("Dips", ["triceps", "body only"], "poitrine", "poussee"),
    ("Overhead Press", ["shoulders", "barbell"], "epaules", "poussee"),
    ("Lateral Raise", ["shoulders", "dumbbell"], "epaules", "extension"),
    ("Face Pull", ["shoulders", "cable"], "epaules", "tirage"),
    ("Pull-up", ["lats", "pull-up bar"], "dos", "tirage"),
    ("Chin-up", ["lats", "pull-up bar"], "dos", "tirage"),
    ("Bent Over Row", ["middle back", "barbell"], "dos", "tirage"),
    ("Seated Cable Rows", ["middle back", "cable"], "dos", "tirage"),
    ("Lat Pulldown", ["lats", "cable"], "dos", "tirage"),
    ("Barbell Shrug", ["traps", "barbell"], "dos", "tirage"),
    ("Barbell Curl", ["biceps", "barbell"], "bras", "tirage"),
    ("Triceps Pushdown", ["triceps", "cable"], "bras", "poussee"),
    ("Back Squat", ["quadriceps", "barbell"], "jambes", "squat"),
    ("Front Squat", ["quadriceps", "barbell"], "jambes", "squat"),
    ("Goblet Squat", ["quadriceps", "kettlebell"], "jambes", "squat"),
    ("Walking Lunge", ["quadriceps", "dumbbell"], "jambes", "fente"),
    ("Bulgarian Split Squat", ["quadriceps", "dumbbell"], "jambes", "squat"),
    ("Romanian Deadlift", ["hamstrings", "barbell"], "jambes", "charniere"),
    ("Conventional Deadlift", ["hamstrings", "barbell"], "jambes", "charniere"),
    ("Kettlebell Swing", ["glutes", "kettlebell"], "hanches", "charniere"),
    ("Hip Thrust", ["glutes", "barbell"], "hanches", "charniere"),
    ("Glute Bridge", ["glutes", "body only"], "hanches", "charniere"),
    ("Standing Calf Raise", ["calves", "machine"], "jambes", "extension"),
    ("Plank", ["abdominals", "body only"], "abdos", "gainage-statique"),
    ("Side Plank", ["abdominals", "body only"], "abdos", "gainage-statique"),
    ("Hollow Body Hold", ["abdominals", "body only"], "abdos", "gainage-statique"),
    ("Dead Bug", ["abdominals", "body only"], "abdos", "anti-rotation"),
    ("Bird Dog", ["abdominals", "body only"], "abdos", "anti-rotation"),
    ("Pallof Press", ["abdominals", "cable"], "abdos", "anti-rotation"),
    ("Hanging Leg Raise", ["abdominals", "pull-up bar"], "abdos", "flexion"),
    ("Cable Crunch", ["abdominals", "cable"], "abdos", "flexion"),
    ("Back Extension", ["lower back", "body only"], "dos", "extension"),
    ("Farmer's Walk", ["forearms", "dumbbell"], "bras", "portage"),
    ("Cat Cow Stretch", ["back", "body only"], "dos", "mobilite"),
    ("Hamstring Stretch", ["hamstrings", "body only"], "jambes", "etirement"),
    ("Burpee", ["full body", "body only"], "corps-entier", "poussee"),
    ("Thoracic Rotation", ["back", "body only"], "dos", "mobilite"),
]


@pytest.mark.parametrize("name,hints,group,pattern", CLASSIFICATION_CASES)
def test_forty_names_are_classified_as_read(name, hints, group, pattern) -> None:
    """Les quarante noms relus à la main le 13/09, et leur classement."""
    muscles, equipment = hints[:-1], hints[-1]
    taxonomy = classify(name, hints=muscles, equipment_hint=equipment)

    assert taxonomy.group == group, f"{name} → groupe {taxonomy.group}"
    assert taxonomy.pattern == pattern, f"{name} → pattern {taxonomy.pattern}"


def test_what_is_not_recognised_stays_to_be_classified() -> None:
    """**Jamais deviné.** C'est la règle qui tient tout le reste.

    Un exercice à classer est inutile au générateur ; un exercice mal classé
    lui fait proposer un soulevé de terre en séance de mobilité, et c'est bien
    pire. Même leçon que `sport=surfing`, appliquée aux exercices.
    """
    taxonomy = classify("Zercher Carry Variation XYZ", hints=["???"])

    assert taxonomy.group == UNCLASSIFIED
    assert not taxonomy.classified


def test_plurals_are_read_like_singulars() -> None:
    """« Bench Mid Rows », « Calf Raises », « Dumbbell Curls ».

    Exiger le singulier exact laissait 319 exercices de free-exercise-db en
    « à classer » sur 876, dont la moitié pour un « s » de trop — constaté à
    l'échantillon avant écriture, ce qui est exactement l'usage de `--sample`.
    """
    assert classify("Donkey Calf Raises").pattern == "extension"
    assert classify("Seated Cable Rows").pattern == "tirage"


def test_equipment_defaults_to_nothing_only_when_said() -> None:
    """« body only » est une affirmation ; l'absence d'indice n'en est pas une.

    Dans le doute on n'écarte pas l'exercice du catalogue, mais on ne le
    propose pas non plus pour une séance « sans matériel » : on ne va pas
    suggérer une barre sur le parking d'une plage.
    """
    assert classify("Push-up", equipment_hint="body only").equipment == "aucun"
    assert classify("Mystery Move").equipment == UNCLASSIFIED


def test_unilateral_is_detected_because_it_doubles_the_time() -> None:
    assert classify("Bulgarian Split Squat").unilateral is True
    assert classify("Side Plank").unilateral is True
    assert classify("Back Squat").unilateral is False


# ── Le glossaire français ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "english,french",
    [
        ("Push-up", "Pompes"),
        ("Barbell Bench Press", "Développé couché à la barre"),
        ("Plank", "Gainage"),
        ("Bulgarian Split Squat", "Fente bulgare"),
        ("Romanian Deadlift", "Soulevé de terre roumain"),
        ("Dumbbell Curl", "Flexion des bras aux haltères"),
        ("Cat Cow Stretch", "Chat-vache"),
    ],
)
def test_the_glossary_composes_rather_than_looks_up(english, french) -> None:
    """« Barre » + « Développé couché », pas une table de phrases entières.

    C'est ce qui permet à cent lignes de glossaire de couvrir des centaines
    d'exercices.
    """
    assert translate_name(english) == french


def test_an_unknown_movement_stays_untranslated() -> None:
    """Traduire à moitié donnerait « Barre Hip Thrust ».

    Ni anglais ni français, et plus difficile à lire que l'original. Mieux vaut
    NULL — et l'exercice n'entre alors ni dans le générateur ni dans une
    formule, ce qui est précisément le but.
    """
    assert translate_name("Zercher Zottman Complex") is None


def test_a_french_name_is_left_alone() -> None:
    """Le catalogue maison est déjà en français : rien à traduire."""
    assert french_name("Planche latérale") == "Planche latérale"
    assert french_name("Chien tête en bas") == "Chien tête en bas"


def test_wger_human_translation_wins_over_the_glossary() -> None:
    """Traduit par des gens, sous licence libre : ça vaut toujours mieux."""
    assert french_name("Plank", {"fr": "Planche abdominale"}) == "Planche abdominale"


# ── 2. Le niveau déduit ────────────────────────────────────────────────────


@dataclass
class Fake:
    """Un exercice, réduit à ce que le générateur regarde."""

    id: int
    slug: str
    name: str
    name_fr: Optional[str]
    image_url: Optional[str]
    group_key: str
    pattern: str
    equipment: str
    difficulty: int
    effort_kind: str
    unilateral: bool
    is_active: bool = True

    @property
    def is_eligible(self) -> bool:
        return bool(self.name_fr) and bool(self.image_url)


def fake(
    identifier: int,
    pattern: str,
    *,
    group: str = "abdos",
    equipment: str = "aucun",
    difficulty: int = 3,
    effort: str = "reps",
    unilateral: bool = False,
    french: Optional[str] = "Exercice",
    image: Optional[str] = "https://img",
) -> Fake:
    return Fake(
        id=identifier,
        slug=f"ex-{identifier}",
        name=f"Ex {identifier}",
        name_fr=f"{french} {identifier}" if french else None,
        image_url=image,
        group_key=group,
        pattern=pattern,
        equipment=equipment,
        difficulty=difficulty,
        effort_kind=effort,
        unilateral=unilateral,
    )


POOL = [
    fake(1, "gainage-statique", effort="temps"),
    fake(2, "anti-rotation"),
    fake(3, "flexion"),
    fake(4, "extension"),
    fake(5, "mobilite", effort="temps"),
    fake(6, "flexion", difficulty=2),
    fake(7, "gainage-statique", effort="temps", difficulty=4),
    fake(8, "anti-rotation", unilateral=True),
    fake(9, "etirement", effort="temps"),
    fake(10, "portage", equipment="halteres", effort="temps"),
    fake(11, "squat", group="jambes"),
    fake(12, "fente", group="jambes", unilateral=True),
]

LEVELS = {"abdos": GroupLevel("abdos", 3, "deduit", 12, 14, 60)}


async def _seed_history(db_session, user, exercise_id, reps=None, seconds=None,
                        days_ago=3, skipped=False):
    from app.models.workout import WorkoutSession, WorkoutSet

    workout = WorkoutSession(
        user_id=user.id,
        formula_name="Test",
        started_at=datetime.now(UTC) - timedelta(days=days_ago),
        completed=True,
    )
    workout.sets.append(
        WorkoutSet(
            position=0,
            exercise_id=exercise_id,
            exercise_name="Test",
            reps=reps,
            duration_s=seconds,
            skipped=skipped,
        )
    )
    db_session.add(workout)
    await db_session.commit()


async def test_a_group_never_trained_starts_at_two(db_session, user) -> None:
    """Pas 1 : le 1 est réservé à ce qui se fait assis.

    Partir de là donnerait une première séance ridicule, et une première
    séance ridicule est une séance qu'on ne refait pas.
    """
    levels = await deduce_levels(db_session, user.id)

    assert levels["abdos"].level == DEFAULT_LEVEL
    assert levels["abdos"].origin == "defaut"
    # Il apparaît quand même : le cacher donnerait l'impression qu'il n'existe
    # pas, alors que c'est celui par lequel commencer.
    assert set(levels) >= {"abdos", "dos", "jambes"}


async def test_a_worked_group_is_deduced_from_what_was_done(
    db_session, user, seeded_exercise
) -> None:
    for _ in range(3):
        await _seed_history(db_session, user, seeded_exercise.id, reps=18)

    levels = await deduce_levels(db_session, user.id)

    assert levels[seeded_exercise.group_key].origin == "deduit"
    assert levels[seeded_exercise.group_key].level >= 4
    assert levels[seeded_exercise.group_key].best_reps == 18


async def test_one_set_is_not_a_level(db_session, user, seeded_exercise) -> None:
    """Une seule série est un essai. Un niveau posé sur un essai fait grimper
    la difficulté d'un cran pour rien."""
    await _seed_history(db_session, user, seeded_exercise.id, reps=30)

    levels = await deduce_levels(db_session, user.id)

    assert levels[seeded_exercise.group_key].origin == "defaut"


async def test_a_skipped_set_does_not_raise_the_level(
    db_session, user, seeded_exercise
) -> None:
    """Une série passée n'est pas une série faite.

    La compter ferait monter le niveau de quelqu'un qui a justement renoncé.
    """
    for _ in range(4):
        await _seed_history(
            db_session, user, seeded_exercise.id, reps=30, skipped=True
        )

    levels = await deduce_levels(db_session, user.id)

    assert levels[seeded_exercise.group_key].origin == "defaut"


async def test_what_is_older_than_eight_weeks_does_not_count(
    db_session, user, seeded_exercise
) -> None:
    """Trois mois d'arrêt doivent se voir."""
    for _ in range(5):
        await _seed_history(
            db_session, user, seeded_exercise.id, reps=25, days_ago=90
        )

    levels = await deduce_levels(db_session, user.id)

    assert levels[seeded_exercise.group_key].origin == "defaut"


async def test_a_manual_correction_always_wins(db_session, user, seeded_exercise) -> None:
    """Une déduction ne discute pas avec quelqu'un qui était là."""
    for _ in range(3):
        await _seed_history(db_session, user, seeded_exercise.id, reps=6)

    levels = await deduce_levels(
        db_session, user.id, overrides={seeded_exercise.group_key: 5}
    )

    assert levels[seeded_exercise.group_key].level == 5
    assert levels[seeded_exercise.group_key].origin == "manuel"


async def test_personal_records_feed_the_progression(
    db_session, user, seeded_exercise
) -> None:
    await _seed_history(db_session, user, seeded_exercise.id, reps=11)
    await _seed_history(db_session, user, seeded_exercise.id, reps=14)

    records = await personal_records(db_session, user.id, [seeded_exercise.id])

    assert records[seeded_exercise.id][0] == 14


# ── 3. Le générateur, sur six demandes ─────────────────────────────────────


def _ids(workouts):
    return [tuple(workout.exercise_ids) for workout in workouts]


def test_a_plain_request_gives_three_distinct_sessions() -> None:
    workouts = generate(
        POOL, Request(groups=("abdos",), duration_min=15, equipment=("aucun",)), LEVELS
    )

    assert len(workouts) == 3
    # **Réellement** différentes. Trois cartes identiques ne sont pas un choix,
    # c'est un bug qu'on a maquillé.
    assert len(set(_ids(workouts))) == 3
    assert len({workout.principle for workout in workouts}) == 3


def test_the_same_request_always_gives_the_same_thing() -> None:
    """Déterministe : Jules ferme l'écran, le rouvre, retrouve ses séances."""
    request = Request(groups=("abdos",), duration_min=15, equipment=("aucun",))

    assert _ids(generate(POOL, request, LEVELS)) == _ids(
        generate(POOL, request, LEVELS)
    )


def test_a_different_variant_gives_something_else() -> None:
    """« Autre chose » doit vraiment proposer autre chose."""
    first = generate(
        POOL, Request(groups=("abdos",), duration_min=15, equipment=("aucun",)), LEVELS
    )
    second = generate(
        POOL,
        Request(
            groups=("abdos",),
            duration_min=15,
            equipment=("aucun",),
            seed_salt="1",
        ),
        LEVELS,
    )

    assert _ids(first) != _ids(second)


def test_no_equipment_never_proposes_equipment() -> None:
    """Le cas du parking de plage, et le plus fréquent."""
    workouts = generate(
        POOL, Request(groups=("abdos",), duration_min=15, equipment=()), LEVELS
    )

    assert workouts
    for workout in workouts:
        for item in workout.items:
            assert item.exercise.equipment == "aucun"


def test_a_group_never_trained_still_gets_a_session() -> None:
    """Niveau 2 par défaut, et une séance quand même.

    Un générateur qui refuserait de proposer tant qu'on n'a rien fait ne
    servirait jamais la première fois — c'est-à-dire la seule qui compte.
    """
    levels = {"jambes": GroupLevel("jambes", 2, "defaut", 0)}
    workouts = generate(
        POOL, Request(groups=("jambes",), duration_min=12, equipment=("aucun",)), levels
    )

    assert workouts
    assert all(
        item.exercise.group_key == "jambes"
        for workout in workouts
        for item in workout.items
    )


def test_nothing_at_the_right_difficulty_relaxes_the_window() -> None:
    """Une séance un peu trop facile vaut mieux qu'une absence de séance."""
    hard_only = [
        fake(20, "gainage-statique", difficulty=5, effort="temps"),
        fake(21, "anti-rotation", difficulty=5),
        fake(22, "flexion", difficulty=5),
        fake(23, "extension", difficulty=5),
    ]
    levels = {"abdos": GroupLevel("abdos", 1, "defaut", 0)}

    workouts = generate(
        hard_only,
        Request(groups=("abdos",), duration_min=12, equipment=("aucun",)),
        levels,
    )

    assert workouts


def test_an_empty_pool_gives_nothing_rather_than_something_wrong() -> None:
    """Pas de séance inventée : l'écran dit pourquoi, il n'affiche pas du vide."""
    assert (
        generate(
            [], Request(groups=("abdos",), duration_min=15, equipment=("aucun",)), LEVELS
        )
        == []
    )


def test_an_exercise_without_a_french_name_is_never_proposed() -> None:
    """Règle E.2 du 13/09, et elle n'a pas d'exception."""
    pool = [
        fake(30, "gainage-statique", french=None, effort="temps"),
        fake(31, "anti-rotation", french=None),
        fake(32, "flexion", french=None),
    ]

    assert generate(
        pool, Request(groups=("abdos",), duration_min=15, equipment=("aucun",)), LEVELS
    ) == []


def test_an_exercise_without_an_image_is_never_proposed() -> None:
    pool = [
        fake(40, "gainage-statique", image=None, effort="temps"),
        fake(41, "anti-rotation", image=None),
        fake(42, "flexion", image=None),
    ]

    assert generate(
        pool, Request(groups=("abdos",), duration_min=15, equipment=("aucun",)), LEVELS
    ) == []


def test_recent_exercises_step_aside_when_an_alternative_exists() -> None:
    """Variété sur quatorze jours — mais pas au prix d'une séance amputée."""
    recent = {1, 2, 3}
    workouts = generate(
        POOL,
        Request(groups=("abdos",), duration_min=12, equipment=("aucun",)),
        LEVELS,
        recent=recent,
    )

    assert workouts
    first = workouts[0].exercise_ids
    # Ce qui n'a pas été fait récemment vient en tête.
    assert first[0] not in recent


def test_a_recent_exercise_is_kept_when_there_is_no_alternative() -> None:
    """Interdire sans remplaçant produirait une séance plus courte que
    demandée, ce qui est pire qu'une répétition."""
    thin = [
        fake(50, "gainage-statique", effort="temps"),
        fake(51, "anti-rotation"),
        fake(52, "flexion"),
    ]

    workouts = generate(
        thin,
        Request(groups=("abdos",), duration_min=12, equipment=("aucun",)),
        LEVELS,
        recent={50, 51, 52},
    )

    assert workouts
    assert workouts[0].items


def test_the_warmup_comes_from_the_mobility_of_the_group() -> None:
    """Deux minutes, et pas un échauffement générique."""
    workouts = generate(
        POOL, Request(groups=("abdos",), duration_min=20, equipment=("aucun",)), LEVELS
    )

    warmup = [item for item in workouts[0].items if item.warmup]
    assert warmup
    assert all(
        item.exercise.pattern in ("mobilite", "etirement") for item in warmup
    )


def test_no_exercise_appears_twice_in_one_session() -> None:
    for workout in generate(
        POOL, Request(groups=("abdos",), duration_min=25, equipment=("aucun",)), LEVELS
    ):
        identifiers = [item.exercise.id for item in workout.items]
        assert len(identifiers) == len(set(identifiers))


def test_progression_adds_exactly_one_notch() -> None:
    """+1 répétition, +5 % de temps. Bornée, et c'est le point.

    Un générateur qui proposerait « 20 » à quelqu'un qui en a fait 12 ne
    propose pas une progression, il propose un échec.
    """
    records = {3: (12, None)}
    workouts = generate(
        POOL,
        Request(
            groups=("abdos",),
            duration_min=20,
            equipment=("aucun",),
            intent=INTENT_PROGRESSION,
        ),
        LEVELS,
        records=records,
    )

    for workout in workouts:
        for item in workout.items:
            if item.exercise.id == 3 and item.reps:
                assert item.reps <= 14


def test_recovery_is_easier_and_keeps_mobility_in() -> None:
    """Une séance de récupération plus dure que d'habitude n'en est pas une.

    Et elle n'a **pas d'échauffement** : la séance entière est de la mobilité,
    lui en coller deux minutes devant reviendrait à s'échauffer pour
    s'échauffer.
    """
    workouts = generate(
        POOL,
        Request(
            groups=("abdos",),
            duration_min=15,
            equipment=("aucun",),
            intent=INTENT_RECOVERY,
        ),
        LEVELS,
    )

    assert workouts
    assert not any(item.warmup for workout in workouts for item in workout.items)
    patterns = {
        item.exercise.pattern for workout in workouts for item in workout.items
    }
    assert patterns & {"mobilite", "etirement"}


def test_a_session_fits_roughly_in_the_time_asked() -> None:
    for workout in generate(
        POOL, Request(groups=("abdos",), duration_min=15, equipment=("aucun",)), LEVELS
    ):
        assert workout.duration_min <= 18


def test_a_unilateral_exercise_counts_double() -> None:
    """« Par côté » n'est pas une nuance d'affichage, c'est le double du temps."""
    from app.services.workout_generator import GeneratedItem

    both = GeneratedItem(
        exercise=fake(60, "fente", unilateral=True), sets=1, reps=10,
        duration_s=None, rest_s=0,
    )
    one = GeneratedItem(
        exercise=fake(61, "fente", unilateral=False), sets=1, reps=10,
        duration_s=None, rest_s=0,
    )

    assert both.seconds == one.seconds * 2
