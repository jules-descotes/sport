"""Habitudes quotidiennes, et statistiques de profil.

⚠️ **Les routes fixes sont déclarées AVANT les routes paramétrées**
(cf. CLAUDE.md) : `/habits/stats` doit précéder `/habits/{habit_id}`.

Le ton de ces écrans est une **contrainte technique** autant qu'éditoriale :
aucune route ne rend de taux de réussite, de série perdue ni de pourcentage
d'objectif manqué. Ce qui sort d'ici est un compteur et une tendance. Une
application qui gronde est une application qu'on désinstalle, et un compteur
qu'on a cessé d'ouvrir ne mesure plus rien.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.habit import Habit, HabitEvent
from app.models.user import User
from app.schemas.habit import (
    HabitEventRead,
    HabitEventWrite,
    HabitRead,
    HabitTrendRead,
    HabitWrite,
    NutritionStatsRead,
    ProfileStats,
    SurfStatsRead,
    TrainingStatsRead,
    WeekCountRead,
)
from app.services.auth_service import get_current_active_user
from app.services.nutrition import daily_target, get_or_create_nutrition_profile
from app.services.stats import (
    habit_trends,
    nutrition_stats,
    surf_stats,
    training_stats,
)

router = APIRouter(tags=["habits"])


def _zone(user: User) -> ZoneInfo:
    name = user.profile.timezone if user.profile else "Europe/Paris"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Paris")


def _bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def _counters(
    db: AsyncSession, habits: list[Habit], today: date, zone: ZoneInfo
) -> tuple[dict[int, float], dict[int, float]]:
    """Les compteurs du jour et de la semaine, en une requête chacun."""
    if not habits:
        return {}, {}

    ids = [habit.id for habit in habits]
    day_start, day_end = _bounds(today, zone)
    week_start, _ = _bounds(today - timedelta(days=today.weekday()), zone)

    async def totals(since: datetime, until: datetime) -> dict[int, float]:
        result = await db.execute(
            select(HabitEvent.habit_id, func.sum(HabitEvent.quantity))
            .where(HabitEvent.habit_id.in_(ids))
            .where(HabitEvent.occurred_at >= since)
            .where(HabitEvent.occurred_at < until)
            .group_by(HabitEvent.habit_id)
        )
        return {habit_id: float(total or 0.0) for habit_id, total in result.all()}

    return await totals(day_start, day_end), await totals(week_start, day_end)


def _read(habit: Habit, today: float, week: float) -> HabitRead:
    return HabitRead(
        **{
            name: getattr(habit, name)
            for name in (
                "id",
                "name",
                "icon",
                "kind",
                "unit",
                "target",
                "target_period",
                "position",
                "is_active",
            )
        },
        today=round(today, 2),
        week=round(week, 2),
    )


# ── Routes fixes ───────────────────────────────────────────────────────────


@router.get("/habits", response_model=list[HabitRead])
async def list_habits(
    include_paused: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[HabitRead]:
    """Les habitudes et leurs compteurs du jour.

    Les habitudes en pause sont exclues par défaut : l'écran Jour ne montre que
    ce qui est en cours. Elles restent visibles depuis le profil, avec leurs
    événements — une pause n'est pas une suppression.
    """
    query = select(Habit).where(Habit.user_id == current_user.id)
    if not include_paused:
        query = query.where(Habit.is_active.is_(True))

    habits = list(
        (await db.execute(query.order_by(Habit.position, Habit.id))).scalars().all()
    )

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    day_totals, week_totals = await _counters(db, habits, today, zone)

    return [
        _read(habit, day_totals.get(habit.id, 0.0), week_totals.get(habit.id, 0.0))
        for habit in habits
    ]


@router.post("/habits", response_model=HabitRead, status_code=status.HTTP_201_CREATED)
async def create_habit(
    data: HabitWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> HabitRead:
    last = (
        await db.execute(
            select(func.coalesce(func.max(Habit.position), -1)).where(
                Habit.user_id == current_user.id
            )
        )
    ).scalar_one()

    habit = Habit(
        user_id=current_user.id,
        **data.model_dump(exclude_none=True, exclude={"position", "is_active"}),
        position=data.position if data.position is not None else int(last) + 1,
    )
    db.add(habit)
    await db.commit()
    await db.refresh(habit)
    return _read(habit, 0.0, 0.0)


@router.get("/habits/stats", response_model=ProfileStats)
async def profile_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileStats:
    """Quatre cartes : surf, nutrition, training, habitudes.

    Rien n'est stocké : tout se recalcule à la lecture. À 240 sessions par an,
    ces requêtes portent sur quelques milliers de lignes, et une table de
    statistiques à tenir à jour serait fausse le jour où l'on corrige une
    session.
    """
    zone = _zone(current_user)
    today = datetime.now(zone).date()
    start, end = _bounds(today, zone)

    nutrition_profile = await get_or_create_nutrition_profile(db, current_user.id)
    target = await daily_target(
        db,
        current_user.id,
        current_user.profile,
        nutrition_profile,
        today,
        start=start,
        end=end,
    )

    surf = await surf_stats(db, current_user.id, today, zone)
    nutrition = await nutrition_stats(db, current_user.id, today, target.kcal)
    training = await training_stats(db, current_user.id, today, zone)
    trends = await habit_trends(db, current_user.id, today, zone)

    return ProfileStats(
        day=today,
        surf=SurfStatsRead(**surf.__dict__),
        nutrition=NutritionStatsRead(**nutrition.__dict__),
        training=TrainingStatsRead(
            weeks=[WeekCountRead(**week.__dict__) for week in training.weeks],
            done_8w=training.done_8w,
            planned_8w=training.planned_8w,
            best_objective=training.best_objective,
            best_ratio=training.best_ratio,
        ),
        habits=[HabitTrendRead(**trend.__dict__) for trend in trends],
    )


# ── Routes paramétrées ─────────────────────────────────────────────────────


async def _get_habit(db: AsyncSession, user_id: int, habit_id: int) -> Habit:
    habit = await db.get(Habit, habit_id)
    if habit is None or habit.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Habitude introuvable"
        )
    return habit


@router.patch("/habits/{habit_id}", response_model=HabitRead)
async def update_habit(
    habit_id: int,
    data: HabitWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> HabitRead:
    """Renomme, change l'icône, l'objectif — ou **met en pause**.

    La pause est le geste important : les événements passés sont de la donnée,
    et une envie du dimanche soir ne doit pas pouvoir effacer trois mois de
    comptage.
    """
    habit = await _get_habit(db, current_user.id, habit_id)

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None or field in ("unit", "target"):
            setattr(habit, field, value)

    await db.commit()
    await db.refresh(habit)

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    day_totals, week_totals = await _counters(db, [habit], today, zone)
    return _read(habit, day_totals.get(habit.id, 0.0), week_totals.get(habit.id, 0.0))


@router.delete("/habits/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(
    habit_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Supprime définitivement, événements compris.

    Le geste normal est la **pause**, et l'écran ne propose celui-ci qu'après.
    Il existe quand même : une habitude créée par erreur le premier jour n'a
    pas à hanter le profil pour toujours.
    """
    habit = await _get_habit(db, current_user.id, habit_id)

    # Les événements partent d'abord, **explicitement**. Le `ON DELETE CASCADE`
    # de la migration ne suffit pas : SQLite n'applique pas les clés étrangères
    # sans `PRAGMA foreign_keys=ON`, et une relation ORM en cascade chargerait
    # trois mille lignes en mémoire pour les supprimer une à une. Un `DELETE`
    # en masse dit ce qu'il fait et marche sur les deux moteurs.
    await db.execute(delete(HabitEvent).where(HabitEvent.habit_id == habit.id))
    await db.delete(habit)
    await db.commit()


@router.post(
    "/habits/{habit_id}/events",
    response_model=HabitRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_habit_event(
    habit_id: int,
    data: HabitEventWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> HabitRead:
    """Un tap. Rend l'habitude **avec son compteur à jour**.

    Rendre l'habitude et non l'événement : l'écran a besoin du compteur, et
    lui faire recharger toute la liste après chaque tap ferait clignoter une
    rangée de pastilles à chaque geste.
    """
    habit = await _get_habit(db, current_user.id, habit_id)

    event = HabitEvent(
        habit_id=habit.id,
        occurred_at=data.occurred_at or datetime.now(UTC),
        quantity=data.quantity,
        note=data.note,
    )
    db.add(event)
    await db.commit()

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    day_totals, week_totals = await _counters(db, [habit], today, zone)
    return _read(habit, day_totals.get(habit.id, 0.0), week_totals.get(habit.id, 0.0))


@router.get("/habits/{habit_id}/events", response_model=list[HabitEventRead])
async def list_habit_events(
    habit_id: int,
    limit: int = Query(default=100, gt=0, le=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[HabitEventRead]:
    """Les événements, du plus récent au plus ancien.

    Horodatés à la seconde : c'est ce qui permettra, au lot 6, de les croiser
    avec le ressenti des sessions du lendemain.
    """
    habit = await _get_habit(db, current_user.id, habit_id)
    result = await db.execute(
        select(HabitEvent)
        .where(HabitEvent.habit_id == habit.id)
        .order_by(HabitEvent.occurred_at.desc())
        .limit(limit)
    )
    return [HabitEventRead.model_validate(row) for row in result.scalars().all()]
