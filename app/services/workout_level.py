"""Le niveau de Jules par groupe — **déduit de ce qu'il a fait**, pas déclaré.

Décidé le 13/09 (retours n° 3). Un générateur de séances doit savoir à quel
point charger : proposer trois séries de tractions lestées à quelqu'un qui en
fait six au poids du corps est inutile, et proposer du gainage de vingt
secondes à quelqu'un qui tient deux minutes l'est tout autant.

**On le déduit, on ne le demande pas.** Un niveau déclaré est une estimation —
souvent optimiste le dimanche soir, pessimiste le lundi matin — et il se périme
sans que personne y touche. `workout_sets` dit ce qui a vraiment été fait, et
il le dit tout seul.

Trois décisions portent le calcul :

1. **Huit semaines glissantes.** Assez pour lisser une mauvaise semaine, assez
   court pour que trois mois d'arrêt se voient. Au-delà, on entraînerait le
   générateur sur un Jules qui n'existe plus.
2. **Un groupe jamais travaillé part au niveau 2**, pas au niveau 1. Le 1 est
   réservé à ce qui se fait assis : partir de là donnerait une première séance
   ridicule, et une première séance ridicule est une séance qu'on ne refait pas.
3. **Corrigeable à la main.** Jules peut se savoir plus fort que ce que son
   historique montre — une reprise après un plâtre, un mois passé à grimper.
   La correction est **persistée** et gagne toujours : une déduction ne discute
   pas avec quelqu'un qui était là.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.models.workout import WorkoutSession, WorkoutSet
from app.services.exercise_taxonomy import GROUPS, UNCLASSIFIED

# Huit semaines glissantes.
WINDOW_DAYS = 56

# Un groupe jamais travaillé. Pas 1 : le 1 est ce qui se fait assis.
DEFAULT_LEVEL = 2

MIN_LEVEL = 1
MAX_LEVEL = 5

# Combien de séries il faut avoir faites pour qu'un niveau soit **déduit**
# plutôt que supposé. Une seule série est un essai, pas un niveau — et un
# niveau posé sur un essai fait grimper la difficulté d'un cran pour rien.
MIN_SETS_FOR_DEDUCTION = 3

# Les repères qui font monter d'un cran. Ils sont grossiers et on l'assume :
# ce qu'on cherche n'est pas une mesure, c'est de savoir dans quelle bande
# proposer (le générateur travaille à ±1 autour du niveau).
#
# `reps` — meilleur nombre de répétitions tenu sur une série ;
# `temps` — meilleure durée tenue, en secondes.
REPS_LADDER = ((6, 2), (10, 3), (16, 4), (24, 5))
TIME_LADDER = ((20, 2), (45, 3), (75, 4), (120, 5))


def _from_ladder(best: float, ladder: tuple[tuple[int, int], ...]) -> int:
    level = MIN_LEVEL
    for threshold, value in ladder:
        if best >= threshold:
            level = value
    return level


@dataclass
class GroupLevel:
    """Le niveau d'un groupe, et **d'où il vient**.

    La provenance est rendue à l'écran : « déduit de 14 séries » se discute,
    « niveau 3 » ne se discute pas. Et un niveau qu'on ne peut pas discuter est
    un niveau qu'on n'ira jamais corriger.
    """

    group: str
    level: int
    # `deduit` · `defaut` · `manuel`
    origin: str
    sets_counted: int = 0
    best_reps: Optional[int] = None
    best_seconds: Optional[int] = None

    @property
    def deduced(self) -> bool:
        return self.origin == "deduit"


async def deduce_levels(
    db: AsyncSession,
    user_id: int,
    *,
    now: Optional[datetime] = None,
    overrides: Optional[dict[str, int]] = None,
) -> dict[str, GroupLevel]:
    """Le niveau de chaque groupe, sur huit semaines glissantes.

    `overrides` porte les corrections manuelles ; elles gagnent toujours. Une
    déduction ne discute pas avec quelqu'un qui était là.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=WINDOW_DAYS)
    manual = overrides or {}

    rows = await db.execute(
        select(
            Exercise.group_key,
            WorkoutSet.reps,
            WorkoutSet.duration_s,
        )
        .join(WorkoutSession, WorkoutSession.id == WorkoutSet.workout_session_id)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.started_at >= since)
        # Une série passée n'est pas une série faite : la compter ferait monter
        # le niveau de quelqu'un qui a justement renoncé.
        .where(WorkoutSet.skipped.is_(False))
    )

    tally: dict[str, dict[str, int]] = {}
    for group, reps, duration_s in rows.all():
        if not group or group == UNCLASSIFIED:
            continue
        bucket = tally.setdefault(
            group, {"sets": 0, "best_reps": 0, "best_seconds": 0}
        )
        bucket["sets"] += 1
        if reps:
            bucket["best_reps"] = max(bucket["best_reps"], int(reps))
        if duration_s:
            bucket["best_seconds"] = max(bucket["best_seconds"], int(duration_s))

    levels: dict[str, GroupLevel] = {}
    for group in GROUPS:
        forced = manual.get(group)
        if forced is not None:
            levels[group] = GroupLevel(
                group=group,
                level=max(MIN_LEVEL, min(MAX_LEVEL, int(forced))),
                origin="manuel",
                sets_counted=tally.get(group, {}).get("sets", 0),
            )
            continue

        bucket = tally.get(group)
        if not bucket or bucket["sets"] < MIN_SETS_FOR_DEDUCTION:
            levels[group] = GroupLevel(
                group=group,
                level=DEFAULT_LEVEL,
                origin="defaut",
                sets_counted=bucket["sets"] if bucket else 0,
            )
            continue

        # Le meilleur des deux échelles : un groupe se travaille au temps ou
        # aux répétitions selon les exercices, et prendre le plus faible des
        # deux punirait celui qui varie.
        candidates = []
        if bucket["best_reps"]:
            candidates.append(_from_ladder(bucket["best_reps"], REPS_LADDER))
        if bucket["best_seconds"]:
            candidates.append(_from_ladder(bucket["best_seconds"], TIME_LADDER))

        levels[group] = GroupLevel(
            group=group,
            level=max(candidates) if candidates else DEFAULT_LEVEL,
            origin="deduit" if candidates else "defaut",
            sets_counted=bucket["sets"],
            best_reps=bucket["best_reps"] or None,
            best_seconds=bucket["best_seconds"] or None,
        )

    return levels


async def personal_records(
    db: AsyncSession,
    user_id: int,
    exercise_ids: list[int],
    *,
    now: Optional[datetime] = None,
) -> dict[int, tuple[Optional[int], Optional[int]]]:
    """Meilleures reps et meilleur temps par exercice, sur la même fenêtre.

    C'est ce qui permet la **progression douce** : +5 % de temps ou +1
    répétition par rapport au dernier record, et rien de plus. Un générateur
    qui proposerait « 20 » à quelqu'un qui en a fait 12 ne propose pas une
    progression, il propose un échec.
    """
    if not exercise_ids:
        return {}

    now = now or datetime.now(UTC)
    since = now - timedelta(days=WINDOW_DAYS)

    rows = await db.execute(
        select(WorkoutSet.exercise_id, WorkoutSet.reps, WorkoutSet.duration_s)
        .join(WorkoutSession, WorkoutSession.id == WorkoutSet.workout_session_id)
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.started_at >= since)
        .where(WorkoutSet.skipped.is_(False))
        .where(WorkoutSet.exercise_id.in_(exercise_ids))
    )

    best: dict[int, tuple[Optional[int], Optional[int]]] = {}
    for exercise_id, reps, duration_s in rows.all():
        current_reps, current_seconds = best.get(exercise_id, (None, None))
        if reps:
            current_reps = max(current_reps or 0, int(reps))
        if duration_s:
            current_seconds = max(current_seconds or 0, int(duration_s))
        best[exercise_id] = (current_reps, current_seconds)
    return best


async def recent_exercise_ids(
    db: AsyncSession,
    user_id: int,
    *,
    days: int = 14,
    now: Optional[datetime] = None,
) -> set[int]:
    """Ce qui a été fait dans les N derniers jours.

    Le générateur les évite **quand une alternative existe** — et seulement
    alors. Interdire un exercice sans remplaçant produirait une séance plus
    courte que demandée, ce qui est pire qu'une répétition.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)

    rows = await db.execute(
        select(WorkoutSet.exercise_id)
        .join(WorkoutSession, WorkoutSession.id == WorkoutSet.workout_session_id)
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.started_at >= since)
        .where(WorkoutSet.exercise_id.is_not(None))
    )
    return {row[0] for row in rows.all() if row[0]}
