"""Composer une séance — **trois**, différentes, et sans LLM.

Décidé le 13/09 (retours n° 3). Entrée : un ou plusieurs groupes, une durée
cible, le matériel disponible, une intention. Sortie : **trois séances
réellement différentes**, chacune avec son principe en une ligne.

Trois choix de conception, et ils se tiennent :

1. **Déterministe.** Même demande, même jour, mêmes trois séances. Ce n'est pas
   une contrainte technique, c'est ce qui rend l'outil testable — et ce qui
   permet à Jules de fermer l'écran et de le rouvrir sans perdre ce qu'il
   venait de voir. Le hasard vient d'une graine construite depuis la demande,
   jamais de l'horloge.
2. **Trois angles, pas trois tirages.** Trois tirages au sort donneraient trois
   séances qui se ressemblent, et on ne saurait pas laquelle choisir. Chaque
   séance part d'un **angle** — une façon d'ordonner les patterns — et
   l'angle est ce que dit le principe en une ligne.
3. **Ce qui n'est pas éligible n'entre pas.** Pas de nom français, pas
   d'image : l'exercice existe dans la bibliothèque et ne sera jamais proposé.
   Une séance se lit à bout de bras, les mains au sol ; un nom anglais demande
   une traduction mentale, une absence d'image demande de se souvenir du
   mouvement, et dans les deux cas on s'arrête.

La progression est **douce et bornée** : +5 % de temps ou +1 répétition sur le
dernier record, jamais plus. Un générateur qui proposerait « 20 » à quelqu'un
qui en a fait 12 ne propose pas une progression, il propose un échec.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.models.exercise import Exercise
from app.services.exercise_taxonomy import (
    EFFORT_TIME,
    GROUP_LABELS,
    PATTERN_LABELS,
    UNCLASSIFIED,
)
from app.services.workout_level import GroupLevel

# ── Intentions ─────────────────────────────────────────────────────────────
#
# Trois, et elles changent vraiment la séance — pas seulement son étiquette.

INTENT_MAINTENANCE = "entretien"
INTENT_PROGRESSION = "progression"
INTENT_RECOVERY = "recuperation"

INTENTS = (INTENT_MAINTENANCE, INTENT_PROGRESSION, INTENT_RECOVERY)

INTENT_LABELS = {
    INTENT_MAINTENANCE: "Entretien",
    INTENT_PROGRESSION: "Progression",
    INTENT_RECOVERY: "Récupération",
}

# Décalage de difficulté par rapport au niveau déduit. La récupération descend
# d'un cran : une séance de récupération plus dure que d'habitude n'est pas une
# séance de récupération.
INTENT_DIFFICULTY_SHIFT = {
    INTENT_MAINTENANCE: 0,
    INTENT_PROGRESSION: 0,
    INTENT_RECOVERY: -1,
}

# ── Repos par pattern, en secondes ─────────────────────────────────────────
#
# Une charnière lourde ne se reprend pas comme un gainage. Le repos est ce qui
# fait tenir une séance de quinze minutes dans quinze minutes — ou pas.
REST_BY_PATTERN = {
    "gainage-statique": 30,
    "anti-rotation": 30,
    "flexion": 25,
    "extension": 30,
    "poussee": 45,
    "tirage": 45,
    "squat": 60,
    "fente": 45,
    "charniere": 60,
    "portage": 45,
    "mobilite": 10,
    "etirement": 5,
}
DEFAULT_REST_S = 30

# ── Échauffement ───────────────────────────────────────────────────────────
#
# Deux minutes, prises dans les exercices de **mobilité du groupe demandé** —
# pas un échauffement générique. Sans mobilité disponible, pas d'échauffement :
# en inventer un avec du renforcement léger serait un contresens.
WARMUP_SECONDS = 120
WARMUP_ITEM_SECONDS = 40

# ── Volume ─────────────────────────────────────────────────────────────────

MIN_ITEMS = 3
MAX_ITEMS = 8
DEFAULT_SETS = 3

# Répétitions et durées de référence, par niveau (1 → 5). Ce sont des points de
# départ, corrigés ensuite par le record personnel quand il existe.
REPS_BY_LEVEL = {1: 6, 2: 8, 3: 10, 4: 12, 5: 15}
SECONDS_BY_LEVEL = {1: 20, 2: 30, 3: 45, 4: 60, 5: 75}

# Progression douce : +5 % de temps, +1 répétition. Bornée, et c'est le point.
PROGRESSION_REPS = 1
PROGRESSION_TIME_RATIO = 1.05


# ── Les trois angles ───────────────────────────────────────────────────────
#
# Chaque angle est un **ordre de préférence de patterns** et une façon de
# remplir le temps. C'est lui qui rend les trois séances distinctes : trois
# tirages au sort donneraient trois variantes de la même chose.


@dataclass(frozen=True)
class Angle:
    key: str
    principle: str
    # Patterns préférés, du plus au moins. Ce qui n'y est pas peut quand même
    # entrer — pour compléter — mais après.
    patterns: tuple[str, ...]
    # Séries par exercice. Un circuit en fait moins, plus longtemps.
    sets: int
    # Multiplicateur de repos. Le circuit enchaîne, le long tient.
    rest_ratio: float
    # Multiplicateur de l'effort (temps ou reps).
    effort_ratio: float


ANGLES: tuple[Angle, ...] = (
    Angle(
        key="tenue",
        principle="Gainage statique long — on tient, on ne compte pas.",
        patterns=("gainage-statique", "anti-rotation", "extension", "portage"),
        sets=3,
        rest_ratio=1.0,
        effort_ratio=1.2,
    ),
    Angle(
        key="mouvement",
        principle="Anti-rotation et flexion — on bouge sous contrôle.",
        patterns=("anti-rotation", "flexion", "charniere", "fente", "tirage"),
        sets=3,
        rest_ratio=1.0,
        effort_ratio=1.0,
    ),
    Angle(
        key="circuit",
        principle="Circuit sans repos — plus court, plus dense.",
        patterns=("squat", "poussee", "tirage", "flexion", "fente", "charniere"),
        sets=2,
        rest_ratio=0.4,
        effort_ratio=0.85,
    ),
)


@dataclass
class GeneratedItem:
    """Une ligne de séance générée. Même forme qu'une `FormulaItem`."""

    exercise: Exercise
    sets: int
    reps: Optional[int]
    duration_s: Optional[int]
    rest_s: int
    note: Optional[str] = None
    # Vrai pour les deux minutes d'échauffement. Affiché à part : un
    # échauffement compté comme une série fausserait le niveau déduit.
    warmup: bool = False

    @property
    def seconds(self) -> int:
        """Le temps que cette ligne prend vraiment, repos compris.

        `unilateral` double l'effort : « par côté » n'est pas une nuance
        d'affichage, c'est le double du temps annoncé.
        """
        effort = self.duration_s or (self.reps or 0) * 3
        if self.exercise.unilateral:
            effort *= 2
        return self.sets * (effort + self.rest_s)


@dataclass
class GeneratedWorkout:
    """Une séance proposée, avec le principe qui la justifie."""

    key: str
    name: str
    principle: str
    items: list[GeneratedItem] = field(default_factory=list)

    @property
    def duration_min(self) -> int:
        total = sum(item.seconds for item in self.items)
        return max(1, round(total / 60))

    @property
    def exercise_ids(self) -> list[int]:
        return [item.exercise.id for item in self.items if not item.warmup]


@dataclass
class Request:
    """Ce que Jules demande. Trois écrans, trois réponses."""

    groups: tuple[str, ...]
    duration_min: int
    equipment: tuple[str, ...]
    intent: str = INTENT_MAINTENANCE
    # Sert la graine, pour que la même demande le même jour rende la même
    # chose. Jamais l'horloge : l'écran serait différent à chaque rendu.
    seed_salt: str = ""

    @property
    def seed(self) -> int:
        raw = "|".join(
            [
                ",".join(sorted(self.groups)),
                str(self.duration_min),
                ",".join(sorted(self.equipment)),
                self.intent,
                self.seed_salt,
            ]
        )
        return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def _fits_equipment(exercise: Exercise, available: Sequence[str]) -> bool:
    """Le matériel demandé, plus « aucun » qui est toujours disponible.

    Un exercice **non classé** en matériel est écarté d'office quand la demande
    est « sans matériel » : dans le doute, on ne propose pas quelque chose qui
    demanderait peut-être une barre sur le parking d'une plage.
    """
    if exercise.equipment == UNCLASSIFIED:
        return False
    if exercise.equipment == "aucun":
        return True
    return exercise.equipment in available


def eligible_pool(
    exercises: Sequence[Exercise],
    request: Request,
) -> list[Exercise]:
    """Ce parmi quoi le générateur a le droit de choisir.

    Quatre filtres, et chacun en écarte pour une raison qu'on peut dire :
    éligible (nom français **et** image), actif, du bon groupe, faisable avec
    ce qu'on a.
    """
    available = tuple(request.equipment) or ("aucun",)
    groups = set(request.groups)
    return [
        exercise
        for exercise in exercises
        if exercise.is_active
        and exercise.is_eligible
        and exercise.group_key in groups
        and exercise.pattern != UNCLASSIFIED
        and _fits_equipment(exercise, available)
    ]


def _difficulty_window(
    exercise: Exercise, levels: dict[str, GroupLevel], intent: str
) -> bool:
    """Difficulté centrée sur le niveau déduit, à ±1.

    En dessous c'est inutile, au-dessus c'est un échec. La récupération décale
    la fenêtre d'un cran vers le bas — une séance de récupération plus dure que
    d'habitude n'en est pas une.
    """
    level = levels.get(exercise.group_key)
    target = (level.level if level else 2) + INTENT_DIFFICULTY_SHIFT.get(intent, 0)
    return abs(exercise.difficulty - target) <= 1


def _effort(
    exercise: Exercise,
    level: int,
    angle: Angle,
    intent: str,
    record: tuple[Optional[int], Optional[int]],
) -> tuple[Optional[int], Optional[int]]:
    """Combien de répétitions, ou combien de secondes.

    Le niveau donne le point de départ ; le **record personnel** le corrige
    quand il existe. En progression, on ajoute exactement un cran : +1
    répétition ou +5 % de temps. Bornée, parce qu'une progression non bornée
    n'est pas une progression.
    """
    best_reps, best_seconds = record

    if exercise.effort_kind == EFFORT_TIME:
        base = best_seconds or SECONDS_BY_LEVEL.get(level, 45)
        value = base * angle.effort_ratio
        if intent == INTENT_PROGRESSION and best_seconds:
            value = max(value, best_seconds * PROGRESSION_TIME_RATIO)
        # Au cran de cinq secondes : personne ne tient « 47 s ».
        return None, max(10, int(round(value / 5)) * 5)

    base = best_reps or REPS_BY_LEVEL.get(level, 10)
    value = base * angle.effort_ratio
    if intent == INTENT_PROGRESSION and best_reps:
        value = max(value, best_reps + PROGRESSION_REPS)
    return max(3, int(round(value))), None


def _ordered(
    pool: Sequence[Exercise], angle: Angle, seed: int
) -> list[Exercise]:
    """Le pool trié par l'angle, puis déterministe sur le reste.

    La clé secondaire est un hachage de `(seed, slug)` : deux demandes
    différentes ne rendent pas la même séance, et la même demande la rend
    toujours. Un `random.shuffle` ferait la même chose en moins lisible et en
    moins reproductible d'une version de Python à l'autre.
    """
    order = {pattern: index for index, pattern in enumerate(angle.patterns)}

    def key(exercise: Exercise) -> tuple[int, str]:
        rank = order.get(exercise.pattern, len(order) + 1)
        digest = hashlib.sha256(
            f"{seed}:{exercise.slug}".encode("utf-8")
        ).hexdigest()
        return (rank, digest)

    return sorted(pool, key=key)


def _warmup(
    pool: Sequence[Exercise], seed: int
) -> list[GeneratedItem]:
    """Deux minutes prises dans la mobilité **du groupe demandé**.

    Pas d'échauffement générique : celui d'une séance d'épaules n'est pas celui
    d'une séance de jambes. Et pas d'échauffement du tout quand le groupe n'a
    aucune mobilité éligible — en fabriquer un avec du renforcement léger
    serait un contresens.
    """
    candidates = [
        exercise
        for exercise in pool
        if exercise.pattern in ("mobilite", "etirement")
    ]
    if not candidates:
        return []

    chosen = sorted(
        candidates,
        key=lambda ex: hashlib.sha256(
            f"warmup:{seed}:{ex.slug}".encode("utf-8")
        ).hexdigest(),
    )[: max(1, WARMUP_SECONDS // WARMUP_ITEM_SECONDS)]

    return [
        GeneratedItem(
            exercise=exercise,
            sets=1,
            reps=None,
            duration_s=WARMUP_ITEM_SECONDS,
            rest_s=0,
            note="échauffement",
            warmup=True,
        )
        for exercise in chosen
    ]


def _compose(
    angle: Angle,
    pool: Sequence[Exercise],
    request: Request,
    levels: dict[str, GroupLevel],
    records: dict[int, tuple[Optional[int], Optional[int]]],
    avoid: set[int],
) -> Optional[GeneratedWorkout]:
    """Une séance, selon un angle. `None` quand le pool ne donne rien."""
    ordered = _ordered(pool, angle, request.seed)

    # Ce qui a été fait dans les quatorze derniers jours passe **derrière**,
    # sans être interdit : un exercice écarté sans remplaçant produirait une
    # séance plus courte que demandée, ce qui est pire qu'une répétition.
    fresh = [ex for ex in ordered if ex.id not in avoid]
    stale = [ex for ex in ordered if ex.id in avoid]
    candidates = fresh + stale
    if not candidates:
        return None

    # **Pas d'échauffement en récupération** : la séance entière est de la
    # mobilité, et lui coller deux minutes de mobilité devant reviendrait à
    # s'échauffer pour s'échauffer. Ça libère au passage ces exercices-là pour
    # le corps de séance, qui n'a que ça à proposer.
    warmup = (
        [] if request.intent == INTENT_RECOVERY else _warmup(pool, request.seed)
    )
    budget = request.duration_min * 60 - sum(item.seconds for item in warmup)

    # La mobilité et les étirements sont le travail de l'échauffement, pas du
    # corps de séance — **sauf en récupération**, où c'est précisément ce qu'on
    # vient chercher. Sans cette règle, un circuit se retrouvait à enchaîner un
    # étirement entre deux gainages, ce qui n'est ni un circuit ni un
    # étirement.
    # Un exercice déjà pris par l'échauffement ne revient pas dans le corps de
    # séance : le voir deux fois donne l'impression d'un générateur qui tourne
    # en rond, et c'est exactement ce qu'il ferait.
    warmup_ids = {item.exercise.id for item in warmup}
    candidates = [ex for ex in candidates if ex.id not in warmup_ids]
    if request.intent != INTENT_RECOVERY:
        candidates = [
            ex
            for ex in candidates
            if ex.pattern not in ("mobilite", "etirement")
        ]
    if not candidates:
        return None

    items: list[GeneratedItem] = []
    used_patterns: list[str] = []
    for exercise in candidates:
        if len(items) >= MAX_ITEMS:
            break
        # Jamais deux fois le même pattern d'affilée : trois gainages de suite
        # ne font pas une séance, ils font un gainage long mal déguisé.
        if used_patterns and used_patterns[-1] == exercise.pattern:
            continue

        level = levels.get(exercise.group_key)
        reps, seconds = _effort(
            exercise,
            level.level if level else 2,
            angle,
            request.intent,
            records.get(exercise.id, (None, None)),
        )
        rest = max(
            5, int(REST_BY_PATTERN.get(exercise.pattern, DEFAULT_REST_S) * angle.rest_ratio)
        )
        item = GeneratedItem(
            exercise=exercise,
            sets=angle.sets,
            reps=reps,
            duration_s=seconds,
            rest_s=rest,
            note="par côté" if exercise.unilateral else None,
        )

        if items and sum(i.seconds for i in items) + item.seconds > budget:
            if len(items) >= MIN_ITEMS:
                break
            # En dessous du minimum, on garde quand même : une séance de deux
            # lignes n'est pas une séance.
        items.append(item)
        used_patterns.append(exercise.pattern)

    if not items:
        return None

    label = " et ".join(GROUP_LABELS.get(g, g) for g in request.groups)
    return GeneratedWorkout(
        key=angle.key,
        name=f"{label} · {INTENT_LABELS.get(request.intent, request.intent)}",
        principle=angle.principle,
        items=warmup + items,
    )


def generate(
    exercises: Sequence[Exercise],
    request: Request,
    levels: dict[str, GroupLevel],
    records: Optional[dict[int, tuple[Optional[int], Optional[int]]]] = None,
    recent: Optional[set[int]] = None,
) -> list[GeneratedWorkout]:
    """Trois séances, aussi différentes que le pool le permet.

    Quand le pool est trop pauvre pour trois séances distinctes, on en rend
    moins — **jamais trois fois la même**. Une liste de trois cartes identiques
    n'est pas un choix, c'est un bug qu'on a maquillé.
    """
    pool = eligible_pool(exercises, request)
    if not pool:
        return []

    # La fenêtre de difficulté d'abord ; si elle vide le pool, on la relâche.
    # Une séance un peu trop facile vaut mieux qu'une absence de séance, et
    # c'est exactement le cas d'un groupe jamais travaillé.
    focused = [
        ex for ex in pool if _difficulty_window(ex, levels, request.intent)
    ]
    working = focused if len(focused) >= MIN_ITEMS else pool

    records = records or {}
    avoid = recent or set()

    workouts: list[GeneratedWorkout] = []
    signatures: set[tuple[int, ...]] = set()
    for angle in ANGLES:
        workout = _compose(angle, working, request, levels, records, avoid)
        if workout is None:
            continue
        signature = tuple(workout.exercise_ids)
        if signature in signatures:
            continue
        signatures.add(signature)
        workouts.append(workout)

    return workouts


def describe(workout: GeneratedWorkout) -> str:
    """Une ligne lisible, pour les logs et les tests."""
    patterns = [
        PATTERN_LABELS.get(item.exercise.pattern, item.exercise.pattern)
        for item in workout.items
        if not item.warmup
    ]
    return f"{workout.name} — {workout.principle} [{', '.join(patterns)}]"
