"""Composer une séance — le générateur, et le niveau qui le règle.

Routes séparées de `/training` pour une raison de lisibilité, pas de
découpage : `training.py` sert déjà les objectifs, les formules, la
bibliothèque et le mode séance, et le générateur y aurait doublé le fichier.
Le préfixe reste `/training` côté client — vu de l'écran, c'est le même écran.

**Rien ici n'appelle de modèle de langue.** L'algorithme est déterministe et
testable : même demande, mêmes trois séances. C'est ce qui permet à Jules de
fermer l'écran et de le rouvrir sans perdre ce qu'il venait de voir, et c'est
ce qui rend les six cas de test possibles.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.exercise import Exercise
from app.models.formula import Formula, FormulaItem
from app.models.profile import Profile
from app.models.user import User
from app.schemas.generator import (
    GenerateRequest,
    GenerateResponse,
    GeneratedItemRead,
    GeneratedWorkoutRead,
    LevelOverride,
    LevelRead,
    SaveGeneratedRequest,
)
from app.schemas.training import ExerciseRead, FormulaRead
from app.services.auth_service import get_current_active_user
from app.services.exercise_taxonomy import (
    EQUIPMENTS,
    GROUP_LABELS,
    GROUPS,
    UNCLASSIFIED,
)
from app.services.training import ensure_training_seeded
from app.services.workout_generator import (
    INTENTS,
    GeneratedWorkout,
    Request,
    generate,
)
from app.services.workout_level import (
    deduce_levels,
    personal_records,
    recent_exercise_ids,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training", tags=["training"])

# Quatorze jours : la fenêtre de variété. Un exercice fait dans les deux
# dernières semaines passe derrière, sans être interdit.
VARIETY_DAYS = 14


def _level_read(level) -> LevelRead:
    return LevelRead(
        group=level.group,
        group_label=GROUP_LABELS.get(level.group, level.group),
        level=level.level,
        origin=level.origin,
        sets_counted=level.sets_counted,
        best_reps=level.best_reps,
        best_seconds=level.best_seconds,
    )


def _overrides(user: User) -> dict[str, int]:
    raw = (user.profile.training_levels if user.profile else None) or {}
    return {
        group: int(value)
        for group, value in raw.items()
        if group in GROUPS and isinstance(value, (int, float))
    }


def _validate(request: GenerateRequest) -> None:
    unknown = [group for group in request.groups if group not in GROUPS]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Groupe inconnu : {', '.join(unknown)}"
        )
    if request.intent not in INTENTS:
        raise HTTPException(
            status_code=422, detail=f"Intention inconnue : {request.intent}"
        )
    bad = [item for item in request.equipment if item not in EQUIPMENTS]
    if bad:
        raise HTTPException(
            status_code=422, detail=f"Matériel inconnu : {', '.join(bad)}"
        )


async def _catalogue(db: AsyncSession, groups: list[str]) -> list[Exercise]:
    result = await db.execute(
        select(Exercise)
        .where(Exercise.is_active.is_(True))
        .where(Exercise.group_key.in_(groups))
    )
    return list(result.scalars().all())


def _why_empty(catalogue: list[Exercise], request: GenerateRequest) -> list[str]:
    """Pourquoi le pool est maigre, en clair.

    Un écran blanc n'apprend rien. « Douze exercices d'abdos, mais aucun avec
    un nom français » dit exactement quoi faire — relancer l'import — et c'est
    la seule chose qu'on puisse dire d'utile à ce moment-là.
    """
    reasons: list[str] = []
    if not catalogue:
        return ["Aucun exercice dans ce groupe — l'import n'a pas été lancé."]

    without_french = sum(1 for ex in catalogue if not ex.name_fr)
    without_image = sum(1 for ex in catalogue if not ex.image_url)
    unclassified = sum(1 for ex in catalogue if ex.pattern == UNCLASSIFIED)

    if without_french:
        reasons.append(f"{without_french} sans nom français")
    if without_image:
        reasons.append(f"{without_image} sans image")
    if unclassified:
        reasons.append(f"{unclassified} à classer")
    return reasons


def _workout_read(workout: GeneratedWorkout) -> GeneratedWorkoutRead:
    return GeneratedWorkoutRead(
        key=workout.key,
        name=workout.name,
        principle=workout.principle,
        duration_min=workout.duration_min,
        items=[
            GeneratedItemRead(
                exercise=ExerciseRead.model_validate(item.exercise),
                sets=item.sets,
                reps=item.reps,
                duration_s=item.duration_s,
                rest_s=item.rest_s,
                note=item.note,
                warmup=item.warmup,
            )
            for item in workout.items
        ],
    )


async def _build(
    db: AsyncSession, user: User, data: GenerateRequest
) -> tuple[list[GeneratedWorkout], list[LevelRead], int, list[str]]:
    _validate(data)
    await ensure_training_seeded(db, user.id)

    catalogue = await _catalogue(db, data.groups)
    levels = await deduce_levels(db, user.id, overrides=_overrides(user))
    records = await personal_records(
        db, user.id, [exercise.id for exercise in catalogue]
    )
    recent = await recent_exercise_ids(db, user.id, days=VARIETY_DAYS)

    request = Request(
        groups=tuple(data.groups),
        duration_min=data.duration_min,
        equipment=tuple(data.equipment),
        intent=data.intent,
        seed_salt=str(data.variant),
    )
    workouts = generate(catalogue, request, levels, records, recent)

    shown = [_level_read(levels[group]) for group in data.groups if group in levels]
    usable = sum(
        1
        for exercise in catalogue
        if exercise.is_eligible and exercise.pattern != UNCLASSIFIED
    )
    return workouts, shown, usable, ([] if workouts else _why_empty(catalogue, data))


# ── Routes fixes, déclarées avant tout `{id}` (cf. CLAUDE.md) ──────────────


@router.get("/levels", response_model=list[LevelRead])
async def read_levels(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[LevelRead]:
    """Le niveau de chaque groupe, et d'où il vient.

    Huit lignes, toujours les mêmes : un groupe jamais travaillé apparaît quand
    même, au niveau 2, marqué « défaut ». Le cacher donnerait l'impression
    qu'il n'existe pas, alors que c'est justement celui par lequel commencer.
    """
    levels = await deduce_levels(db, current_user.id, overrides=_overrides(current_user))
    return [_level_read(levels[group]) for group in GROUPS if group in levels]


@router.put("/levels", response_model=list[LevelRead])
async def set_level(
    data: LevelOverride,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[LevelRead]:
    """Corriger un niveau à la main, ou rendre la main à la déduction.

    `level: null` **efface** la correction. C'est le geste « en fait non,
    reprends ce que tu vois » ; sans lui, une correction posée un dimanche
    resterait vraie pour toujours.
    """
    if data.group not in GROUPS:
        raise HTTPException(status_code=422, detail="Groupe inconnu")

    profile = current_user.profile
    if profile is None:
        profile = Profile(user_id=current_user.id)
        db.add(profile)
        current_user.profile = profile

    stored = dict(profile.training_levels or {})
    if data.level is None:
        stored.pop(data.group, None)
    else:
        stored[data.group] = int(data.level)
    # Réaffectation et pas mutation : SQLAlchemy ne voit pas changer le contenu
    # d'une colonne JSON modifiée sur place, et la correction serait perdue au
    # commit sans rien signaler.
    profile.training_levels = stored or None

    await db.commit()

    # Les corrections sont relues depuis `stored`, pas depuis l'utilisateur
    # rechargé : après le commit, la relation `profile` est expirée, et y
    # toucher hors du contexte greenlet de SQLAlchemy async lève. On a la
    # valeur sous la main, on s'en sert.
    overrides = {
        group: int(value) for group, value in stored.items() if group in GROUPS
    }
    levels = await deduce_levels(db, current_user.id, overrides=overrides)
    return [_level_read(levels[group]) for group in GROUPS if group in levels]


@router.post("/compose", response_model=GenerateResponse)
async def compose(
    data: GenerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    """Trois séances, ou moins — **jamais trois fois la même**.

    Une liste de trois cartes identiques n'est pas un choix, c'est un bug qu'on
    a maquillé. Quand le catalogue est trop pauvre, on en rend moins et on dit
    pourquoi : « douze exercices d'abdos, mais aucun avec un nom français » dit
    exactement quoi faire, là où un écran blanc n'apprend rien.
    """
    workouts, levels, pool_size, reasons = await _build(db, current_user, data)
    return GenerateResponse(
        workouts=[_workout_read(workout) for workout in workouts],
        levels=levels,
        pool_size=pool_size,
        reasons=reasons,
    )


@router.post(
    "/compose/save", response_model=FormulaRead, status_code=status.HTTP_201_CREATED
)
async def save_generated(
    data: SaveGeneratedRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FormulaRead:
    """Sauver une séance générée comme **formule personnelle**.

    Régénérée depuis la demande plutôt que renvoyée par le client : le client
    pourrait envoyer n'importe quoi, et une formule est de la donnée
    d'apprentissage. Le générateur étant déterministe, la même demande rend la
    même séance — c'est ce qui rend ce choix gratuit.
    """
    request = GenerateRequest(
        groups=data.groups,
        duration_min=data.duration_min,
        equipment=data.equipment,
        intent=data.intent,
        variant=data.variant,
    )
    workouts, _, _, _ = await _build(db, current_user, request)

    chosen = next((w for w in workouts if w.key == data.key), None)
    if chosen is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Séance introuvable — recompose-la.",
        )

    slug = _unique_slug(data.name)
    existing = await db.execute(select(Formula).where(Formula.slug == slug))
    if existing.scalar_one_or_none() is not None:
        slug = f"{slug}-{data.variant + 1}"

    formula = Formula(
        slug=slug,
        name=data.name,
        duration_min=chosen.duration_min,
        weekly_target=1,
        principle=chosen.principle,
        objective_slugs=[],
        tags=["composee"],
        # Pas de `variant_of` : une formule composée est sa propre famille. La
        # rattacher à une famille existante fausserait le compte hebdomadaire
        # de cette famille-là.
        variant_of=None,
    )
    for position, item in enumerate(chosen.items, start=1):
        formula.items.append(
            FormulaItem(
                position=position,
                exercise_id=item.exercise.id,
                sets=item.sets,
                reps=item.reps,
                duration_s=item.duration_s,
                rest_s=item.rest_s,
                note=item.note,
            )
        )

    db.add(formula)
    await db.commit()
    await db.refresh(formula)
    return FormulaRead.model_validate(formula)


def _unique_slug(name: str) -> str:
    import re
    import unicodedata

    stripped = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")
    return slug or "seance"
