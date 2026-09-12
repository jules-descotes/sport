"""Routes du training — objectifs mesurés, formules, mode séance.

⚠️ **Les routes fixes sont déclarées AVANT les routes paramétrées**
(cf. CLAUDE.md) : `/training/overview` doit précéder tout `{id}`, sinon
FastAPI tente de lire « overview » comme un identifiant et renvoie 422.

Le semis du catalogue a lieu **au premier accès**, pas au démarrage : le
conteneur Railway redémarre à froid plusieurs fois par jour, et refaire ce
travail à chaque démarrage retarderait la première réponse pour rien.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.exercise import Exercise
from app.models.formula import Formula
from app.models.objective import Objective, ObjectiveMeasurement
from app.models.user import User
from app.models.workout import WorkoutSession, WorkoutSet
from app.schemas.training import (
    ExerciseRead,
    FormulaRead,
    MeasurementCreate,
    ObjectiveRead,
    ProposalRead,
    TrainingOverview,
    WorkoutFinish,
    WorkoutRead,
    WorkoutStart,
)
from app.services.auth_service import get_current_active_user
from app.services.training import (
    COMPLETION_RATIO,
    Proposal,
    ensure_training_seeded,
    objective_progress,
    propose_today,
    weekly_counts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training", tags=["training"])


def _timezone(user: User) -> str:
    return user.profile.timezone if user.profile else "Europe/Paris"


def _local_today(user: User) -> date:
    try:
        return datetime.now(ZoneInfo(_timezone(user))).date()
    except Exception:
        return datetime.now(UTC).date()


def _objective_read(objective: Objective, today: date) -> ObjectiveRead:
    progress = objective_progress(objective, today)
    return ObjectiveRead(
        id=objective.id,
        slug=objective.slug,
        name=objective.name,
        measure=objective.measure,
        unit=objective.unit,
        direction=objective.direction,
        target_value=objective.target_value,
        start_value=progress.start_value,
        current_value=progress.current_value,
        ratio=progress.ratio,
        last_measured_on=objective.last_measured_on,
        measure_every_days=objective.measure_every_days,
        needs_measurement=progress.needs_measurement,
        measurements=list(objective.measurements),
    )


def _formula_read(formula: Formula, done: dict[str, int]) -> FormulaRead:
    return FormulaRead(
        id=formula.id,
        slug=formula.slug,
        name=formula.name,
        duration_min=formula.duration_min,
        weekly_target=formula.weekly_target,
        principle=formula.principle,
        objective_slugs=list(formula.objective_slugs or []),
        tags=list(formula.tags or []),
        variant_of=formula.variant_of,
        family=formula.family,
        items=list(formula.items),
        done_this_week=done.get(formula.family, 0),
    )


def _proposal_read(proposal: Proposal, done: dict[str, int]) -> ProposalRead:
    return ProposalRead(
        formula=(
            _formula_read(proposal.formula, done) if proposal.formula else None
        ),
        reason=proposal.reason,
        alternatives=[
            _formula_read(formula, done) for formula in proposal.alternatives
        ],
        surf_streak=proposal.surf_streak,
    )


# ── Routes fixes ───────────────────────────────────────────────────────────


@router.get("/overview", response_model=TrainingOverview)
async def training_overview(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TrainingOverview:
    """Tout l'écran Training en un aller-retour.

    Quatre requêtes séparées coûteraient quatre allers-retours sur un écran
    qu'on ouvre debout, sur un réseau de parking de plage.
    """
    await ensure_training_seeded(db, current_user.id)

    today = _local_today(current_user)
    timezone = _timezone(current_user)

    objectives = (
        (
            await db.execute(
                select(Objective)
                .where(Objective.user_id == current_user.id)
                .where(Objective.is_active.is_(True))
                .order_by(Objective.position)
            )
        )
        .scalars()
        .all()
    )
    formulas = (
        (
            await db.execute(
                select(Formula)
                .where(Formula.is_active.is_(True))
                .order_by(Formula.position)
            )
        )
        .scalars()
        .all()
    )
    recent = (
        (
            await db.execute(
                select(WorkoutSession)
                .where(WorkoutSession.user_id == current_user.id)
                .order_by(WorkoutSession.started_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    done = await weekly_counts(db, current_user.id, today, timezone)
    proposal = await propose_today(db, current_user.id, today, timezone)

    return TrainingOverview(
        objectives=[_objective_read(objective, today) for objective in objectives],
        formulas=[_formula_read(formula, done) for formula in formulas],
        proposal=_proposal_read(proposal, done),
        recent=[WorkoutRead.model_validate(item) for item in recent],
    )


@router.get("/today", response_model=ProposalRead)
async def training_today(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProposalRead:
    """La proposition du jour, seule — ce que l'écran Jour affiche.

    Un appel distinct et léger : l'écran Jour n'a pas besoin des jauges, de la
    bibliothèque ni de l'historique, et il est déjà le plus chargé de l'app.
    """
    await ensure_training_seeded(db, current_user.id)

    today = _local_today(current_user)
    timezone = _timezone(current_user)
    done = await weekly_counts(db, current_user.id, today, timezone)
    proposal = await propose_today(db, current_user.id, today, timezone)
    return _proposal_read(proposal, done)


@router.get("/objectives", response_model=list[ObjectiveRead])
async def list_objectives(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[ObjectiveRead]:
    await ensure_training_seeded(db, current_user.id)
    today = _local_today(current_user)

    result = await db.execute(
        select(Objective)
        .where(Objective.user_id == current_user.id)
        .order_by(Objective.position)
    )
    return [
        _objective_read(objective, today) for objective in result.scalars().all()
    ]


@router.get("/formulas", response_model=list[FormulaRead])
async def list_formulas(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[FormulaRead]:
    await ensure_training_seeded(db, current_user.id)

    done = await weekly_counts(
        db, current_user.id, _local_today(current_user), _timezone(current_user)
    )
    result = await db.execute(
        select(Formula).where(Formula.is_active.is_(True)).order_by(Formula.position)
    )
    return [_formula_read(formula, done) for formula in result.scalars().all()]


@router.get("/exercises", response_model=list[ExerciseRead])
async def list_exercises(
    q: Optional[str] = Query(default=None, max_length=80),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=100, gt=0, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExerciseRead]:
    """La bibliothèque, consultable. Source et licence sur chaque ligne."""
    await ensure_training_seeded(db, current_user.id)

    from sqlalchemy import func as sa_func

    query = select(Exercise).where(Exercise.is_active.is_(True))
    if category:
        query = query.where(Exercise.category == category)
    if q:
        query = query.where(
            sa_func.lower(Exercise.name_normalized).like(f"%{q.strip().lower()}%")
        )

    result = await db.execute(query.order_by(Exercise.name).limit(limit))
    return [
        ExerciseRead.model_validate(exercise) for exercise in result.scalars().all()
    ]


@router.get("/workouts", response_model=list[WorkoutRead])
async def list_workouts(
    limit: int = Query(default=50, gt=0, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkoutRead]:
    result = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .order_by(WorkoutSession.started_at.desc())
        .limit(limit)
    )
    return [WorkoutRead.model_validate(item) for item in result.scalars().all()]


@router.post(
    "/workouts", response_model=WorkoutRead, status_code=status.HTTP_201_CREATED
)
async def start_workout(
    data: WorkoutStart,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> WorkoutRead:
    """Ouvre une séance. Le nom de la formule est **figé** à cet instant.

    Une formule renommée ou retouchée plus tard ne doit pas réécrire
    l'historique : ce qui a été fait a été fait sous ce nom-là, avec ce
    contenu-là.
    """
    formula = (
        await db.execute(select(Formula).where(Formula.id == data.formula_id))
    ).scalar_one_or_none()
    if formula is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Formule introuvable"
        )

    workout = WorkoutSession(
        user_id=current_user.id,
        formula_id=formula.id,
        formula_name=formula.name,
        formula_family=formula.family,
        started_at=(data.started_at or datetime.now(UTC)).astimezone(UTC),
    )
    db.add(workout)
    await db.commit()
    await db.refresh(workout)
    return WorkoutRead.model_validate(workout)


# ── Routes paramétrées ─────────────────────────────────────────────────────


@router.post(
    "/objectives/{objective_id}/measurements",
    response_model=ObjectiveRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_measurement(
    objective_id: int,
    data: MeasurementCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ObjectiveRead:
    """Une mesure datée.

    Une par jour et par objectif : se remesurer le même jour remplace la
    valeur, ce qui est la lecture naturelle (« c'était mal fait la première
    fois »). Deux chiffres pour la même chose le même jour ne veulent rien dire.
    """
    objective = (
        await db.execute(
            select(Objective)
            .where(Objective.id == objective_id)
            .where(Objective.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if objective is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Objectif introuvable"
        )

    day = data.measured_on or _local_today(current_user)
    existing = next(
        (item for item in objective.measurements if item.measured_on == day), None
    )
    if existing is not None:
        existing.value = data.value
        existing.note = data.note
    else:
        db.add(
            ObjectiveMeasurement(
                objective_id=objective.id,
                measured_on=day,
                value=data.value,
                note=data.note,
            )
        )

    await db.commit()
    await db.refresh(objective)
    return _objective_read(objective, _local_today(current_user))


@router.get("/workouts/{workout_id}", response_model=WorkoutRead)
async def read_workout(
    workout_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> WorkoutRead:
    return WorkoutRead.model_validate(
        await _get_workout(db, current_user.id, workout_id)
    )


@router.post("/workouts/{workout_id}/finish", response_model=WorkoutRead)
async def finish_workout(
    workout_id: int,
    data: WorkoutFinish,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> WorkoutRead:
    """Clôt une séance — et **décide elle-même** si elle est complète.

    C'est le point qui fait que ces lignes valent quelque chose. Une séance de
    28 minutes arrêtée à la sixième est un renseignement : la formule est trop
    longue, ou mal placée dans la semaine. La compter comme faite effacerait
    exactement l'information qui permettrait de la corriger — et la
    proposition du jour continuerait de la servir.

    Le client ne déclare donc pas « complète » : le serveur compte les séries
    réellement faites face à ce que la formule prévoyait. Au-delà de 80 %, la
    séance est faite — s'arrêter au dernier étirement d'une souplesse longue
    n'est pas un abandon.
    """
    workout = await _get_workout(db, current_user.id, workout_id)
    if workout.ended_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Séance déjà terminée"
        )

    workout.sets.clear()
    for entry in data.sets:
        workout.sets.append(
            WorkoutSet(
                formula_item_id=entry.formula_item_id,
                exercise_id=entry.exercise_id,
                exercise_name=entry.exercise_name,
                position=entry.position,
                reps=entry.reps,
                duration_s=entry.duration_s,
                skipped=entry.skipped,
            )
        )

    planned = sum(item.sets for item in workout.formula.items) if workout.formula else 0
    done = sum(1 for entry in data.sets if not entry.skipped)
    ratio = (done / planned) if planned else (1.0 if done else 0.0)

    workout.ended_at = (data.ended_at or datetime.now(UTC)).astimezone(UTC)
    workout.completed = ratio >= COMPLETION_RATIO
    workout.cut_short = not workout.completed
    workout.feeling = data.feeling
    workout.notes = data.notes

    await db.commit()
    await db.refresh(workout)
    return WorkoutRead.model_validate(workout)


@router.delete("/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(
    workout_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Supprime une séance ouverte par erreur.

    Pas de corbeille ici, contrairement aux sessions de surf : une séance de
    mobilité n'est pas une ligne d'apprentissage du modèle de goût, et le seul
    cas réel est « j'ai tapé Commencer par erreur ».
    """
    workout = await _get_workout(db, current_user.id, workout_id)
    await db.delete(workout)
    await db.commit()


async def _get_workout(
    db: AsyncSession, user_id: int, workout_id: int
) -> WorkoutSession:
    workout = (
        await db.execute(
            select(WorkoutSession)
            .where(WorkoutSession.id == workout_id)
            .where(WorkoutSession.user_id == user_id)
        )
    ).scalar_one_or_none()
    if workout is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Séance introuvable"
        )
    return workout
