"""Recomposer les formules avec des exercices qu'on peut lire et voir.

Décidé le 13/09 (retours n° 4), règle E.2 : **un exercice sans nom français ou
sans image n'entre ni dans le générateur ni dans une formule.** Les quinze
formules du lot 4 ont été écrites avant cette règle ; certaines de leurs lignes
pointent sur des exercices maison qui n'ont toujours pas d'image.

Ce module remplace ces lignes-là, et **liste ce qu'il a remplacé**. La liste
compte autant que le remplacement : une formule qui change sous les doigts sans
qu'on sache ce qui a bougé n'est plus une formule à laquelle on se fie.

Le remplaçant est cherché dans cet ordre :

1. **Même groupe, même pattern, même matériel, difficulté la plus proche.**
   C'est le même travail, fait autrement.
2. **Même groupe, même pattern.** Le matériel tombe.
3. **Même pattern seul.** Dernier recours : le mouvement compte plus que le
   muscle pour ce que la formule cherche à produire.

**Aucun remplaçant trouvé = la ligne reste.** Une formule amputée d'un exercice
est moins bonne qu'une formule avec une ligne sans image : la séance se fait
quand même, et on sait quoi corriger. Supprimer silencieusement laisserait une
formule de trois minutes là où il y en avait douze.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.models.formula import Formula, FormulaItem
from app.services.exercise_taxonomy import UNCLASSIFIED

logger = logging.getLogger(__name__)


@dataclass
class Replacement:
    """Une ligne remplacée — ou une ligne qu'on n'a pas su remplacer."""

    formula_slug: str
    formula_name: str
    position: int
    removed_slug: str
    removed_name: str
    reason: str
    replaced_by_slug: Optional[str] = None
    replaced_by_name: Optional[str] = None
    how: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.replaced_by_slug is not None


def _why_ineligible(exercise: Exercise) -> Optional[str]:
    missing = []
    if not exercise.name_fr:
        missing.append("pas de nom français")
    if not exercise.image_url:
        missing.append("pas d'image")
    return " et ".join(missing) or None


def _candidates(
    target: Exercise, pool: list[Exercise], used: set[int]
) -> list[tuple[str, Exercise]]:
    """Les remplaçants possibles, du plus proche au plus lointain."""
    if target.pattern == UNCLASSIFIED:
        return []

    def sorted_by_difficulty(rows: list[Exercise]) -> list[Exercise]:
        return sorted(
            rows,
            key=lambda ex: (abs(ex.difficulty - target.difficulty), ex.slug),
        )

    same_everything = [
        ex
        for ex in pool
        if ex.id not in used
        and ex.group_key == target.group_key
        and ex.pattern == target.pattern
        and ex.equipment == target.equipment
    ]
    same_group = [
        ex
        for ex in pool
        if ex.id not in used
        and ex.group_key == target.group_key
        and ex.pattern == target.pattern
    ]
    same_pattern = [
        ex for ex in pool if ex.id not in used and ex.pattern == target.pattern
    ]

    out: list[tuple[str, Exercise]] = []
    for how, rows in (
        ("groupe+pattern+materiel", same_everything),
        ("groupe+pattern", same_group),
        ("pattern", same_pattern),
    ):
        for row in sorted_by_difficulty(rows):
            out.append((how, row))
    return out


async def repair_formulas(
    db: AsyncSession, *, dry_run: bool = False
) -> list[Replacement]:
    """Remplace les lignes inéligibles des formules. Rend la liste, toujours.

    Idempotent : une formule déjà saine ne change pas, et relancer ne produit
    aucune ligne de plus.
    """
    exercises = list((await db.execute(select(Exercise))).scalars().all())
    by_id = {exercise.id: exercise for exercise in exercises}
    pool = [
        exercise
        for exercise in exercises
        if exercise.is_active
        and exercise.is_eligible
        and exercise.pattern != UNCLASSIFIED
    ]

    formulas = list(
        (
            await db.execute(
                select(Formula).options(selectinload(Formula.items))
            )
        )
        .scalars()
        .all()
    )

    replacements: list[Replacement] = []
    changed = False

    for formula in formulas:
        used = {item.exercise_id for item in formula.items}
        for item in sorted(formula.items, key=lambda row: row.position):
            exercise = by_id.get(item.exercise_id)
            if exercise is None:
                continue
            reason = _why_ineligible(exercise)
            if reason is None:
                continue

            replacement = Replacement(
                formula_slug=formula.slug,
                formula_name=formula.name,
                position=item.position,
                removed_slug=exercise.slug,
                removed_name=exercise.name,
                reason=reason,
            )

            candidates = _candidates(exercise, pool, used)
            if candidates:
                how, donor = candidates[0]
                replacement.replaced_by_slug = donor.slug
                replacement.replaced_by_name = donor.display_name
                replacement.how = how
                used.discard(item.exercise_id)
                used.add(donor.id)
                if not dry_run:
                    item.exercise_id = donor.id
                    # Le tempo et la note décrivaient **l'ancien** exercice.
                    # Les garder ferait dire à la nouvelle ligne quelque chose
                    # qui n'est plus vrai.
                    item.note = None
                    item.tempo = None
                    changed = True

            replacements.append(replacement)

    if changed and not dry_run:
        await db.commit()

    logger.info(
        "Formules : %d lignes inéligibles, %d remplacées",
        len(replacements),
        sum(1 for item in replacements if item.resolved),
    )
    return replacements
