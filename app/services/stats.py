"""Les statistiques du profil — quatre cartes, des chiffres, aucune morale.

Décidé le 13/09. Ce ne sont pas encore les statistiques du lot 6 (« tes
meilleures sessions : houle 1,2–1,8 m, période 11–14 s, marée montante »), qui
demandent une analyse des corrélations. Ce sont les chiffres qu'on a déjà et
qu'on n'a jamais montrés : combien de sessions, combien d'heures, quel spot,
quelle moyenne.

Trois principes :

1. **Rien n'est stocké.** Tout se recalcule à la lecture. À 240 sessions par an
   ces requêtes portent sur quelques milliers de lignes, et une table de
   statistiques à tenir à jour serait fausse le jour où l'on corrige une
   session.
2. **Une absence est une absence.** Aucun zéro de complaisance : une moyenne
   sans session vaut `None`, et l'écran écrit « — ». Un zéro se lirait comme
   une mauvaise note.
3. **Aucun jugement.** Les habitudes remontent une tendance sur trente jours,
   pas un taux de réussite. Ce sont des compteurs, pas des devoirs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SessionStatus
from app.models.formula import Formula
from app.models.habit import Habit, HabitEvent
from app.models.nutrition import BodyMetric, FoodLog
from app.models.objective import Objective, ObjectiveMeasurement
from app.models.spot import Spot
from app.models.surf_session import SurfSession
from app.models.workout import WorkoutSession

# Les fenêtres du produit. Trente jours pour « en ce moment », la saison pour
# « cette année » — et la saison de surf commence en septembre, pas en janvier.
RECENT_DAYS = 30
TREND_DAYS = 30
WEEKS = 8
SEASON_START_MONTH = 9


def season_start(today: date) -> date:
    """Le 1er septembre de la saison en cours.

    Une saison de surf ne commence pas le 1er janvier : elle commence quand les
    houles d'automne reviennent. Compter en année civile couperait la meilleure
    période en deux.
    """
    year = today.year if today.month >= SEASON_START_MONTH else today.year - 1
    return date(year, SEASON_START_MONTH, 1)


def _bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# ── Surf ───────────────────────────────────────────────────────────────────


@dataclass
class SurfStats:
    sessions_30d: int = 0
    hours_30d: float = 0.0
    sessions_season: int = 0
    hours_season: float = 0.0
    # `None` et pas 0 : une moyenne sans session n'existe pas.
    average_rating: Optional[float] = None
    top_spot: Optional[str] = None
    top_spot_sessions: int = 0
    # Jours consécutifs avec au moins une session, en comptant depuis
    # aujourd'hui ou hier — pas depuis le dernier jour surfé, sinon une série
    # d'il y a trois mois s'afficherait comme si elle était en cours.
    streak_days: int = 0
    best_rating: Optional[float] = None
    best_spot: Optional[str] = None
    best_day: Optional[date] = None


def current_streak(days: Sequence[date], today: date) -> int:
    """Jours consécutifs surfés, en cours **aujourd'hui**.

    La série démarre à aujourd'hui ou à hier — pas plus loin. Sinon une série
    de douze jours terminée en mars s'afficherait tout l'été comme si elle
    durait encore, ce qui serait flatteur et faux.
    """
    surfed = set(days)
    if today not in surfed and (today - timedelta(days=1)) not in surfed:
        return 0

    cursor = today if today in surfed else today - timedelta(days=1)
    streak = 0
    while cursor in surfed:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def surf_stats(
    db: AsyncSession, user_id: int, today: date, zone: ZoneInfo
) -> SurfStats:
    recent_from, _ = _bounds(today - timedelta(days=RECENT_DAYS), zone)
    season_from, _ = _bounds(season_start(today), zone)

    result = await db.execute(
        select(SurfSession)
        .where(SurfSession.user_id == user_id)
        .where(SurfSession.deleted_at.is_(None))
        .where(SurfSession.started_at >= season_from)
        .order_by(SurfSession.started_at)
    )
    sessions = list(result.scalars().all())
    if not sessions:
        return SurfStats()

    spot_names = {
        spot_id: name
        for spot_id, name in (
            await db.execute(
                select(Spot.id, Spot.name).where(
                    Spot.id.in_({session.spot_id for session in sessions})
                )
            )
        ).all()
    }

    stats = SurfStats()
    ratings: list[float] = []
    per_spot: dict[int, int] = {}
    surfed_days: list[date] = []

    for session in sessions:
        started = _utc(session.started_at)
        minutes = session.duration_min or 0
        stats.sessions_season += 1
        stats.hours_season += minutes / 60.0
        if started >= recent_from:
            stats.sessions_30d += 1
            stats.hours_30d += minutes / 60.0

        per_spot[session.spot_id] = per_spot.get(session.spot_id, 0) + 1
        surfed_days.append(started.astimezone(zone).date())

        if session.rating_conditions_half is not None:
            rating = session.rating_conditions_half / 2
            ratings.append(rating)
            if stats.best_rating is None or rating > stats.best_rating:
                stats.best_rating = rating
                stats.best_spot = spot_names.get(session.spot_id)
                stats.best_day = started.astimezone(zone).date()

    stats.hours_30d = round(stats.hours_30d, 1)
    stats.hours_season = round(stats.hours_season, 1)
    stats.average_rating = (
        round(sum(ratings) / len(ratings), 2) if ratings else None
    )

    if per_spot:
        top_id = max(per_spot, key=lambda key: per_spot[key])
        stats.top_spot = spot_names.get(top_id)
        stats.top_spot_sessions = per_spot[top_id]

    stats.streak_days = current_streak(surfed_days, today)
    return stats


# ── Nutrition ──────────────────────────────────────────────────────────────


@dataclass
class NutritionStats:
    logged_days_30d: int = 0
    # Journées dont le total tombe à moins de 10 % de la cible. Un intervalle
    # et pas une égalité : personne ne mange 2 431 kcal.
    on_target_days_30d: int = 0
    average_protein_g: Optional[float] = None
    weight_kg: Optional[float] = None
    weight_change_30d: Optional[float] = None


# Tolérance autour de la cible. Dix pour cent : c'est la précision réelle d'un
# journal alimentaire tenu à la main, et exiger mieux ne mesurerait plus que la
# rigueur de la pesée.
TARGET_TOLERANCE = 0.10


async def nutrition_stats(
    db: AsyncSession,
    user_id: int,
    today: date,
    target_kcal: Optional[int],
) -> NutritionStats:
    since = today - timedelta(days=RECENT_DAYS)

    result = await db.execute(
        select(
            FoodLog.day,
            func.sum(FoodLog.kcal),
            func.sum(FoodLog.protein_g),
        )
        .where(FoodLog.user_id == user_id)
        .where(FoodLog.day >= since)
        .group_by(FoodLog.day)
    )
    rows = result.all()

    stats = NutritionStats(logged_days_30d=len(rows))
    proteins = [protein for _, _, protein in rows if protein is not None]
    if proteins:
        stats.average_protein_g = round(sum(proteins) / len(proteins), 1)

    if target_kcal:
        low = target_kcal * (1 - TARGET_TOLERANCE)
        high = target_kcal * (1 + TARGET_TOLERANCE)
        stats.on_target_days_30d = sum(
            1 for _, kcal, _ in rows if kcal is not None and low <= kcal <= high
        )

    weights = (
        await db.execute(
            select(BodyMetric.day, BodyMetric.weight_kg)
            .where(BodyMetric.user_id == user_id)
            .where(BodyMetric.weight_kg.is_not(None))
            .order_by(BodyMetric.day.desc())
            .limit(20)
        )
    ).all()
    if weights:
        stats.weight_kg = weights[0][1]
        older = [entry for entry in weights if entry[0] <= since]
        if older:
            stats.weight_change_30d = round(stats.weight_kg - older[0][1], 1)

    return stats


# ── Training ───────────────────────────────────────────────────────────────


@dataclass
class WeekCount:
    week_start: date
    done: int
    planned: int


@dataclass
class TrainingStats:
    weeks: list[WeekCount] = field(default_factory=list)
    done_8w: int = 0
    planned_8w: int = 0
    best_objective: Optional[str] = None
    best_ratio: Optional[float] = None


async def training_stats(
    db: AsyncSession, user_id: int, today: date, zone: ZoneInfo
) -> TrainingStats:
    """Séances faites contre séances prévues, sur huit semaines.

    « Prévues » est la somme des `weekly_target` des familles de formules : ce
    que l'app a proposé, pas ce que Jules s'était juré. Comparer à un
    engagement moral serait exactement le jugement qu'on s'interdit.
    """
    monday = today - timedelta(days=today.weekday())
    first_monday = monday - timedelta(weeks=WEEKS - 1)
    start, _ = _bounds(first_monday, zone)

    planned_per_week = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(Formula.weekly_target), 0)).where(
                    Formula.variant_of.is_(None)
                )
            )
        ).scalar_one()
        or 0
    )

    result = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.started_at >= start)
        .where(WorkoutSession.completed.is_(True))
    )

    per_week: dict[date, int] = {}
    for workout in result.scalars().all():
        local = _utc(workout.started_at).astimezone(zone).date()
        week = local - timedelta(days=local.weekday())
        per_week[week] = per_week.get(week, 0) + 1

    stats = TrainingStats()
    for index in range(WEEKS):
        week = first_monday + timedelta(weeks=index)
        done = per_week.get(week, 0)
        stats.weeks.append(
            WeekCount(week_start=week, done=done, planned=planned_per_week)
        )
        stats.done_8w += done
        stats.planned_8w += planned_per_week

    # L'objectif le plus avancé — celui qui donne envie de continuer. Le plus
    # en retard est déjà mis en avant sur l'écran Training ; le répéter ici
    # ferait deux reproches pour un.
    objectives = (
        await db.execute(select(Objective).where(Objective.user_id == user_id))
    ).scalars().all()

    for objective in objectives:
        measurements = (
            await db.execute(
                select(ObjectiveMeasurement)
                .where(ObjectiveMeasurement.objective_id == objective.id)
                .order_by(ObjectiveMeasurement.measured_on)
            )
        ).scalars().all()
        if len(measurements) < 2 or objective.target_value is None:
            continue

        start_value = measurements[0].value
        current = measurements[-1].value
        span = objective.target_value - start_value
        if span == 0:
            continue
        ratio = max(0.0, min(1.0, (current - start_value) / span))
        if stats.best_ratio is None or ratio > stats.best_ratio:
            stats.best_ratio = round(ratio, 2)
            stats.best_objective = objective.name

    return stats


# ── Habitudes ──────────────────────────────────────────────────────────────


@dataclass
class HabitTrend:
    habit_id: int
    name: str
    icon: str
    unit: Optional[str]
    kind: str
    total_30d: float = 0.0
    days_with_activity: int = 0
    # Une valeur par jour sur trente jours, du plus ancien au plus récent.
    # C'est la courbe, et **rien d'autre** : pas de série, pas de pourcentage
    # de réussite. On observe, on n'évalue pas.
    daily: list[float] = field(default_factory=list)


async def habit_trends(
    db: AsyncSession,
    user_id: int,
    today: date,
    zone: ZoneInfo,
    days: int = TREND_DAYS,
) -> list[HabitTrend]:
    habits = (
        await db.execute(
            select(Habit)
            .where(Habit.user_id == user_id)
            .order_by(Habit.position, Habit.id)
        )
    ).scalars().all()
    if not habits:
        return []

    first = today - timedelta(days=days - 1)
    start, _ = _bounds(first, zone)

    events = (
        await db.execute(
            select(HabitEvent)
            .where(HabitEvent.habit_id.in_([habit.id for habit in habits]))
            .where(HabitEvent.occurred_at >= start)
        )
    ).scalars().all()

    per_habit: dict[int, dict[date, float]] = {}
    for event in events:
        day = _utc(event.occurred_at).astimezone(zone).date()
        per_habit.setdefault(event.habit_id, {}).setdefault(day, 0.0)
        per_habit[event.habit_id][day] += event.quantity

    trends: list[HabitTrend] = []
    for habit in habits:
        by_day = per_habit.get(habit.id, {})
        daily = [
            round(by_day.get(first + timedelta(days=index), 0.0), 2)
            for index in range(days)
        ]
        trends.append(
            HabitTrend(
                habit_id=habit.id,
                name=habit.name,
                icon=habit.icon,
                unit=habit.unit,
                kind=habit.kind,
                total_30d=round(sum(daily), 2),
                days_with_activity=sum(1 for value in daily if value > 0),
                daily=daily,
            )
        )
    return trends
