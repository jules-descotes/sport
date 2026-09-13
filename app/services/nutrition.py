"""La cible calorique du jour — et sa correction par la balance.

« Calories suivant entraînement » a été traduit en **cible recalibrée**
(PROJET.md §10.6) : Mifflin-St Jeor, plus un facteur d'activité de base, plus
la dépense estimée du jour, moins ou plus l'objectif — et le tout **corrigé
toutes les deux à trois semaines sur l'évolution réelle du poids**.

Cette dernière partie n'est pas un raffinement, c'est ce qui rend le reste
honnête. L'estimation calorique d'une session de surf est très approximative :
le compendium d'activités physiques donne 3 MET pour « surf, général », d'autres
sources 5 ou 6, et la vérité dépend du nombre de vagues, de la distance de
rame et du temps passé assis à attendre. Plutôt que de choisir un chiffre et
d'y croire, on choisit un chiffre **plausible** et on mesure l'erreur sur la
balance.

La cible n'est donc **jamais stockée**. Elle se recalcule à chaque lecture. La
figer voudrait dire la recalculer à la main à chaque pesée, c'est-à-dire
l'oublier.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import BodyMetric, NutritionProfile
from app.models.profile import Profile
from app.models.surf_session import SurfSession
from app.models.workout import WorkoutSession

logger = logging.getLogger(__name__)

# ── Constantes physiologiques ──────────────────────────────────────────────

# Mifflin-St Jeor (1990), la formule de référence pour le métabolisme de base.
# Elle bat Harris-Benedict sur les populations modernes, et c'est la seule
# raison pour laquelle elle est ici.
MSJ_WEIGHT = 10.0
MSJ_HEIGHT = 6.25
MSJ_AGE = 5.0
MSJ_MALE_OFFSET = 5.0
MSJ_FEMALE_OFFSET = -161.0

# Contenu énergétique d'un kilo de tissu adipeux. ~7 700 kcal : c'est la
# constante qui traduit un déficit cumulé en kilos, et donc l'écart de poids
# en erreur de cible.
KCAL_PER_KG = 7700.0

# Objectifs. Un déficit léger et pas agressif : à 240 sessions de surf par an,
# un déficit de 700 kcal ferait perdre la rame avant le gras.
GOAL_KCAL = {"maintain": 0.0, "cut": -350.0, "bulk": 250.0}

# MET du surf, par tranche de durée. Le compendium donne 3,0 pour « surf,
# général » et 5,0 pour « compétition » ; la vérité d'une session libre est
# entre les deux, et elle **décroît** : la première heure est une heure de
# rame, la troisième une heure d'attente. Trois paliers valent mieux qu'une
# moyenne, et de toute façon la calibration rattrape ce qui reste.
SURF_MET_BY_HOUR = ((1.0, 5.0), (2.0, 4.0), (99.0, 3.0))

# MET des séances de training, par famille de formule.
WORKOUT_MET = {"mobility": 2.5, "core": 3.5, "strength": 5.0}
WORKOUT_MET_DEFAULT = 3.0

# Le métabolisme de base tourne pendant la session aussi : une heure de surf ne
# coûte pas MET × poids, elle coûte (MET − 1) × poids de plus que rien faire.
# Oublier ce « −1 » surestime la dépense de 20 à 30 %.
RESTING_MET = 1.0

# Macros : 4 kcal par gramme de protéines et de glucides, 9 pour les lipides.
KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0

# ── Recalibration ──────────────────────────────────────────────────────────

# En deçà, on ne corrige pas : une variation de poids sur dix jours est du
# contenu digestif et de l'eau, pas du tissu.
MIN_CALIBRATION_DAYS = 14
# Au-delà, la fenêtre mélange trop de choses (un voyage, une semaine malade).
MAX_CALIBRATION_DAYS = 28
# Correction maximale par passe. Une correction de 600 kcal d'un coup ferait
# osciller la cible d'une pesée à l'autre au lieu de converger.
MAX_CALIBRATION_STEP_KCAL = 200.0
# Plafond absolu du terme appris : au-delà, ce n'est plus une calibration,
# c'est que le profil est faux.
MAX_CALIBRATION_KCAL = 800.0


def basal_metabolic_rate(
    weight_kg: float, height_cm: float, age_years: float, sex: Optional[str]
) -> float:
    """Mifflin-St Jeor. `sex` inconnu : on prend la moyenne des deux.

    Prendre la moyenne plutôt que de supposer un sexe est la seule réponse
    honnête à un champ vide, et l'écart (166 kcal) est du même ordre que ce que
    la calibration rattrape en deux semaines.
    """
    base = MSJ_WEIGHT * weight_kg + MSJ_HEIGHT * height_cm - MSJ_AGE * age_years
    if sex == "male":
        return base + MSJ_MALE_OFFSET
    if sex == "female":
        return base + MSJ_FEMALE_OFFSET
    return base + (MSJ_MALE_OFFSET + MSJ_FEMALE_OFFSET) / 2.0


def surf_met(duration_min: float) -> float:
    """MET **moyen** d'une session de surf de cette durée.

    Décroissant par paliers : la première heure est une heure de rame, la
    troisième une heure d'attente. On pondère les paliers par le temps passé
    dans chacun, ce qui donne une moyenne continue plutôt qu'une marche
    d'escalier à 60 minutes pile.
    """
    hours = max(0.0, duration_min) / 60.0
    if hours == 0:
        return 0.0

    total = 0.0
    previous = 0.0
    for edge, met in SURF_MET_BY_HOUR:
        span = min(hours, edge) - previous
        if span <= 0:
            break
        total += span * met
        previous = min(hours, edge)
    return total / hours


def activity_kcal(met: float, weight_kg: float, duration_min: float) -> float:
    """Dépense **supplémentaire** d'une activité, en kilocalories.

    « Supplémentaire » : on retranche le métabolisme de repos, qui tournait de
    toute façon. Une heure à 5 MET ne coûte pas 5 × poids, elle coûte
    4 × poids de plus que de rester assis. Oublier ce détail surestime la
    dépense de 20 à 30 % — et sur une année de surf, ça fait plusieurs kilos
    de cible qui n'existent pas.
    """
    return max(0.0, met - RESTING_MET) * weight_kg * (duration_min / 60.0)


@dataclass
class DayExpenditure:
    """Ce que la journée a coûté en plus du train-train."""

    surf_min: int = 0
    surf_kcal: float = 0.0
    workout_min: int = 0
    workout_kcal: float = 0.0

    @property
    def total_kcal(self) -> float:
        return self.surf_kcal + self.workout_kcal


@dataclass
class Target:
    """La cible du jour, et de quoi elle est faite.

    Le détail n'est pas de la décoration : une cible qui monte de 400 kcal sans
    dire pourquoi n'est pas croyable, et une cible pas croyable ne se suit pas.
    """

    kcal: int
    protein_g: int
    carb_g: int
    fat_g: int

    bmr: float
    base_kcal: float
    expenditure: DayExpenditure
    goal_kcal: float
    calibration_kcal: float
    # Vrai quand il a fallu se rabattre sur des valeurs par défaut : l'écran le
    # dit plutôt que de faire passer une estimation pour un calcul.
    estimated: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def protein_g_per_kg(self) -> Optional[float]:
        return None


def macro_split(
    kcal: float, weight_kg: float, protein_g_per_kg: float, fat_ratio: float
) -> tuple[int, int, int]:
    """Protéines, glucides, lipides — dans cet ordre de priorité.

    Les protéines d'abord, parce qu'elles se fixent au poids de corps et pas
    aux calories : 1,8 g/kg est 1,8 g/kg qu'on soit en déficit ou non. Les
    lipides ensuite, en part des calories, avec un plancher implicite par le
    ratio. Les glucides prennent ce qui reste — ce sont eux la variable
    d'ajustement, et c'est le bon choix quand on rame deux heures par jour.
    """
    protein_g = max(0.0, protein_g_per_kg * weight_kg)
    fat_g = max(0.0, kcal * fat_ratio / KCAL_PER_G_FAT)

    used = protein_g * KCAL_PER_G_PROTEIN + fat_g * KCAL_PER_G_FAT
    carb_g = max(0.0, (kcal - used) / KCAL_PER_G_CARB)

    return int(round(protein_g)), int(round(carb_g)), int(round(fat_g))


def age_years(birth_date: Optional[date], today: Optional[date] = None) -> Optional[float]:
    if birth_date is None:
        return None
    today = today or date.today()
    return (today - birth_date).days / 365.25


# ── Lecture de la journée ──────────────────────────────────────────────────

# Valeurs de repli quand le profil est vide. Elles sont **plausibles et
# annoncées comme telles** : une cible refusée faute de taille laisserait
# l'écran vide, et un écran vide ne se remplit jamais.
DEFAULT_WEIGHT_KG = 75.0
DEFAULT_HEIGHT_M = 1.78
DEFAULT_AGE = 35.0


async def latest_weight(
    db: AsyncSession, user_id: int, before: Optional[date] = None
) -> Optional[float]:
    """Le dernier poids pesé. C'est lui qui prime sur celui du profil.

    Le profil porte un poids saisi une fois ; la balance en porte un tous les
    dimanches. Prendre le profil reviendrait à calculer la cible de cette
    semaine sur le poids d'il y a six mois.
    """
    query = (
        select(BodyMetric.weight_kg)
        .where(BodyMetric.user_id == user_id)
        .where(BodyMetric.weight_kg.is_not(None))
        .order_by(BodyMetric.day.desc())
        .limit(1)
    )
    if before is not None:
        query = query.where(BodyMetric.day <= before)
    return (await db.execute(query)).scalar_one_or_none()


async def get_or_create_nutrition_profile(
    db: AsyncSession, user_id: int
) -> NutritionProfile:
    result = await db.execute(
        select(NutritionProfile).where(NutritionProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = NutritionProfile(user_id=user_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def day_expenditure(
    db: AsyncSession,
    user_id: int,
    day: date,
    weight_kg: float,
    *,
    start: datetime,
    end: datetime,
) -> DayExpenditure:
    """La dépense sportive d'une journée : surf et séances.

    Les bornes sont passées en UTC par l'appelant, qui seul connaît le fuseau
    de l'utilisateur — une journée est une notion locale.
    """
    expenditure = DayExpenditure()

    sessions = await db.execute(
        select(SurfSession)
        .where(SurfSession.user_id == user_id)
        .where(SurfSession.deleted_at.is_(None))
        .where(SurfSession.started_at >= start)
        .where(SurfSession.started_at < end)
    )
    for session in sessions.scalars().all():
        minutes = session.duration_min or 0
        if minutes <= 0:
            continue
        expenditure.surf_min += minutes
        expenditure.surf_kcal += activity_kcal(
            surf_met(minutes), weight_kg, minutes
        )

    workouts = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.started_at >= start)
        .where(WorkoutSession.started_at < end)
    )
    for workout in workouts.scalars().all():
        minutes = workout.duration_min or 0
        if minutes <= 0:
            continue
        met = WORKOUT_MET.get(workout.formula_family or "", WORKOUT_MET_DEFAULT)
        expenditure.workout_min += minutes
        expenditure.workout_kcal += activity_kcal(met, weight_kg, minutes)

    return expenditure


async def daily_target(
    db: AsyncSession,
    user_id: int,
    profile: Optional[Profile],
    nutrition: NutritionProfile,
    day: date,
    *,
    start: datetime,
    end: datetime,
) -> Target:
    """La cible du jour, avec le détail de son calcul."""
    reasons: list[str] = []
    estimated = False

    weight_kg = await latest_weight(db, user_id, day)
    if weight_kg is None:
        weight_kg = profile.weight_kg if profile else None
    if weight_kg is None:
        weight_kg = DEFAULT_WEIGHT_KG
        estimated = True
        reasons.append("poids estimé — pèse-toi pour affiner")

    height_m = (profile.height_m if profile else None) or DEFAULT_HEIGHT_M
    if profile is None or profile.height_m is None:
        estimated = True
        reasons.append("taille estimée")

    age = age_years(profile.birth_date if profile else None, day)
    if age is None:
        age = DEFAULT_AGE
        estimated = True
        reasons.append("âge estimé")

    bmr = basal_metabolic_rate(
        weight_kg, height_m * 100.0, age, profile.sex if profile else None
    )
    base_kcal = bmr * nutrition.activity_factor

    expenditure = await day_expenditure(
        db, user_id, day, weight_kg, start=start, end=end
    )
    goal_kcal = GOAL_KCAL.get(nutrition.goal, 0.0)

    total = (
        base_kcal
        + expenditure.total_kcal
        + goal_kcal
        + nutrition.calibration_kcal
    )
    # Un plancher, et il n'est pas décoratif : un jour sans sport, en déficit,
    # avec une calibration négative, la formule peut descendre sous 1 200 kcal,
    # ce qui n'est pas une cible, c'est un régime.
    total = max(1200.0, total)

    protein_g, carb_g, fat_g = macro_split(
        total, weight_kg, nutrition.protein_g_per_kg, nutrition.fat_ratio
    )

    return Target(
        kcal=int(round(total)),
        protein_g=protein_g,
        carb_g=carb_g,
        fat_g=fat_g,
        bmr=round(bmr, 1),
        base_kcal=round(base_kcal, 1),
        expenditure=expenditure,
        goal_kcal=goal_kcal,
        calibration_kcal=nutrition.calibration_kcal,
        estimated=estimated,
        reasons=reasons,
    )


# ── La correction par la balance ───────────────────────────────────────────


@dataclass
class Calibration:
    """Le résultat d'une passe de recalibration."""

    applied: bool
    days: int = 0
    weight_change_kg: float = 0.0
    expected_change_kg: float = 0.0
    adjustment_kcal: float = 0.0
    new_calibration_kcal: float = 0.0
    reason: str = ""


def compute_calibration(
    *,
    current_kcal: float,
    days: int,
    weight_change_kg: float,
    goal_kcal: float,
    logged_ratio: float = 1.0,
) -> Calibration:
    """L'écart entre le poids prédit et le poids réel, traduit en kilocalories.

    Le raisonnement tient en une ligne : si l'objectif était de perdre 350 kcal
    par jour et que le poids n'a pas bougé en trois semaines, c'est que la cible
    était trop haute de 350 kcal par jour. On corrige donc de l'écart, mais
    **pas de tout l'écart d'un coup** : une correction de 600 kcal ferait
    osciller la cible d'une pesée à l'autre au lieu de converger.

    `logged_ratio` est la part des jours effectivement journalisés sur la
    fenêtre. En dessous de la moitié, on ne corrige pas : l'écart mesure alors
    ce qui n'a pas été noté, pas ce qui a été mangé — et corriger sur ce
    signal-là reviendrait à punir l'oubli.
    """
    if days < MIN_CALIBRATION_DAYS:
        return Calibration(
            applied=False,
            days=days,
            reason=f"moins de {MIN_CALIBRATION_DAYS} jours entre deux pesées",
        )
    if logged_ratio < 0.5:
        return Calibration(
            applied=False,
            days=days,
            reason="moins de la moitié des jours journalisés",
        )

    # Ce que l'objectif prévoyait sur la fenêtre.
    expected_change_kg = goal_kcal * days / KCAL_PER_KG

    # Le surplus quotidien : combien de kilocalories par jour ont été gardées
    # **en plus** de ce qu'on avait prédit. Positif = on a moins maigri que
    # prévu, donc le modèle surestime la dépense.
    surplus_kcal = (weight_change_kg - expected_change_kg) * KCAL_PER_KG / days

    # Et la correction est **l'opposé** du surplus. Le sens compte plus que
    # tout le reste de cette fonction, et il n'est pas intuitif :
    #
    #   trois semaines de déficit, zéro kilo perdu
    #     -> on a gardé 350 kcal/jour de plus que prévu
    #     -> notre cible était trop haute de 350
    #     -> on la **baisse**.
    #
    # Se tromper de signe ici ferait diverger la cible au lieu de la faire
    # converger, et l'erreur ne se verrait qu'au bout de trois pesées.
    adjustment = max(
        -MAX_CALIBRATION_STEP_KCAL, min(MAX_CALIBRATION_STEP_KCAL, -surplus_kcal)
    )
    new_value = max(
        -MAX_CALIBRATION_KCAL,
        min(MAX_CALIBRATION_KCAL, current_kcal + adjustment),
    )

    return Calibration(
        applied=True,
        days=days,
        weight_change_kg=round(weight_change_kg, 2),
        expected_change_kg=round(expected_change_kg, 2),
        adjustment_kcal=round(adjustment, 1),
        new_calibration_kcal=round(new_value, 1),
        reason="calibrée sur la variation de poids",
    )


async def recalibrate(
    db: AsyncSession,
    user_id: int,
    nutrition: NutritionProfile,
    *,
    today: Optional[date] = None,
    logged_days: Optional[int] = None,
) -> Calibration:
    """Relit les pesées et corrige `calibration_kcal` si la fenêtre s'y prête.

    Appelée à chaque pesée. Elle ne fait rien la plupart du temps, et c'est
    voulu : corriger toutes les semaines transformerait le bruit de la balance
    en oscillation de la cible.
    """
    today = today or date.today()
    horizon = today - timedelta(days=MAX_CALIBRATION_DAYS)

    result = await db.execute(
        select(BodyMetric)
        .where(BodyMetric.user_id == user_id)
        .where(BodyMetric.weight_kg.is_not(None))
        .where(BodyMetric.day >= horizon)
        .order_by(BodyMetric.day)
    )
    weigh_ins: Sequence[BodyMetric] = list(result.scalars().all())
    if len(weigh_ins) < 2:
        return Calibration(applied=False, reason="deux pesées sont nécessaires")

    first, last = weigh_ins[0], weigh_ins[-1]
    days = (last.day - first.day).days
    ratio = 1.0 if logged_days is None or days == 0 else logged_days / days

    calibration = compute_calibration(
        current_kcal=nutrition.calibration_kcal,
        days=days,
        weight_change_kg=(last.weight_kg or 0.0) - (first.weight_kg or 0.0),
        goal_kcal=GOAL_KCAL.get(nutrition.goal, 0.0),
        logged_ratio=ratio,
    )

    if calibration.applied:
        nutrition.calibration_kcal = calibration.new_calibration_kcal
        nutrition.calibrated_on = today
        await db.commit()
        logger.info(
            "Cible recalibrée de %+.0f kcal sur %d jours",
            calibration.adjustment_kcal,
            calibration.days,
        )

    return calibration
