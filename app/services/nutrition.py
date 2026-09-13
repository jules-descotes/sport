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

# **Le socle : 3 MET.** C'est « surf, général » au compendium d'activités
# physiques, et c'est la seule valeur de tout ce fichier qui vienne d'une
# source publiée. Tout le reste est une modulation, et chaque modulation est
# une hypothèse qu'on assume (décidé le 13/09, retours n° 4).
SURF_MET_BASE = 3.0

# Modulation par la **durée**. Elle décroît : la première heure est une heure
# de rame, la troisième une heure d'attente. Trois paliers valent mieux qu'une
# moyenne, et la calibration par la balance rattrape ce qui reste.
SURF_MET_BY_HOUR = ((1.0, 2.0), (2.0, 1.0), (99.0, 0.0))

# Modulation par la **taille des vagues déclarée** sur la session (retours
# n° 4). Ramer dans du gros n'est pas la même activité que glisser dans du
# petit, et c'est justement ce que le type de vagues permet enfin de savoir.
#
# Une taille **non renseignée vaut zéro**, comme « petites » : c'est le choix
# prudent. Deviner « moyennes » par défaut gonflerait la cible calorique de
# toutes les sessions décrites par personne — et une cible trop haute ne se
# voit pas, elle se mange.
SURF_MET_BY_WAVE_SIZE = {"small": 0.0, "medium": 1.0, "large": 2.0}

# MET des séances de training, par **pattern dominant** de la formule.
#
# Le pattern est déduit des catégories des exercices qui la composent : une
# formule majoritairement de mobilité coûte ce que coûtent des étirements, une
# formule de renfo coûte ce que coûte du renfo. La famille sert de repli quand
# la formule n'est plus là — une séance garde le nom de sa formule même si
# celle-ci est supprimée (`formula_family` est figé à la création).
WORKOUT_MET = {"mobility": 2.5, "core": 3.5, "strength": 5.0}
WORKOUT_MET_DEFAULT = 3.0

# Ce qui apparaît dans le détail, en français et en clair. Une ligne « MET 6,0 »
# ne renseigne personne ; « grandes vagues » dit exactement pourquoi le chiffre
# est ce qu'il est.
WAVE_SIZE_LABELS = {
    "small": "petites vagues",
    "medium": "vagues moyennes",
    "large": "grandes vagues",
}

PATTERN_LABELS = {
    "mobility": "mobilité",
    "core": "gainage",
    "strength": "renfo",
}

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


def surf_met(
    duration_min: float, wave_size: Optional[str] = None
) -> float:
    """MET **moyen** d'une session de surf : socle, durée, taille des vagues.

    `3 + bonus de durée + bonus de taille`. Le bonus de durée est décroissant
    et pondéré par le temps passé dans chaque palier, ce qui donne une moyenne
    continue plutôt qu'une marche d'escalier à soixante minutes pile.

    Sans taille déclarée, le bonus de vagues est **nul** — comme pour des
    petites. C'est volontairement prudent : deviner « moyennes » gonflerait la
    cible de toutes les sessions que personne n'a décrites, et une cible trop
    haute ne se voit pas, elle se mange.
    """
    hours = max(0.0, duration_min) / 60.0
    if hours == 0:
        return 0.0

    total = 0.0
    previous = 0.0
    for edge, bonus in SURF_MET_BY_HOUR:
        span = min(hours, edge) - previous
        if span <= 0:
            break
        total += span * bonus
        previous = min(hours, edge)

    duration_bonus = total / hours
    wave_bonus = SURF_MET_BY_WAVE_SIZE.get(wave_size or "", 0.0)
    return SURF_MET_BASE + duration_bonus + wave_bonus


def activity_kcal(met: float, weight_kg: float, duration_min: float) -> float:
    """Dépense **supplémentaire** d'une activité, en kilocalories.

    « Supplémentaire » : on retranche le métabolisme de repos, qui tournait de
    toute façon. Une heure à 5 MET ne coûte pas 5 × poids, elle coûte
    4 × poids de plus que de rester assis. Oublier ce détail surestime la
    dépense de 20 à 30 % — et sur une année de surf, ça fait plusieurs kilos
    de cible qui n'existent pas.
    """
    return max(0.0, met - RESTING_MET) * weight_kg * (duration_min / 60.0)



async def dominant_patterns(
    db: AsyncSession, formula_ids: Sequence[int]
) -> dict[int, str]:
    """Le pattern dominant de chaque formule, en une requête.

    « Dominant » = la catégorie d'exercice la plus représentée parmi ses
    lignes. C'est grossier, et c'est assez : une formule de mobilité ne coûte
    pas ce que coûte du renfo, et c'est tout ce que la dépense a besoin de
    savoir. Le jour où les exercices porteront un vrai pattern de mouvement,
    c'est **ici** que ça se branche, et nulle part ailleurs.

    En une requête et pas une par séance : une journée à deux séances en ferait
    déjà trois allers-retours pour une information de trois mots.
    """
    ids = [identifier for identifier in set(formula_ids) if identifier]
    if not ids:
        return {}

    from app.models.exercise import Exercise
    from app.models.formula import FormulaItem

    rows = await db.execute(
        select(FormulaItem.formula_id, Exercise.category)
        .join(Exercise, Exercise.id == FormulaItem.exercise_id)
        .where(FormulaItem.formula_id.in_(ids))
    )

    counts: dict[int, dict[str, int]] = {}
    for formula_id, category in rows.all():
        bucket = counts.setdefault(formula_id, {})
        bucket[category] = bucket.get(category, 0) + 1

    return {
        formula_id: max(bucket.items(), key=lambda pair: pair[1])[0]
        for formula_id, bucket in counts.items()
        if bucket
    }

@dataclass
class ExpenditureItem:
    """Une ligne du détail : ce qu'on a fait, combien de temps, ce que ça coûte.

    Le détail existe parce qu'une estimation sans décomposition ne se corrige
    pas. « 620 kcal » ne dit pas si c'est la session de trois heures ou la
    séance de renfo qui pèse, donc ne dit pas quoi rectifier quand le chiffre
    paraît faux — et un chiffre qu'on ne peut pas rectifier, on cesse de le
    lire (décidé le 13/09, retours n° 4).
    """

    kind: str  # "surf" ou "workout"
    label: str
    minutes: int
    met: float
    kcal: float
    # Ce qui a modulé le MET, en clair : « grandes vagues », « renfo ». Rendu
    # tel quel à l'écran.
    detail: Optional[str] = None


@dataclass
class DayExpenditure:
    """Ce que la journée a coûté en plus du train-train."""

    surf_min: int = 0
    surf_kcal: float = 0.0
    workout_min: int = 0
    workout_kcal: float = 0.0
    items: list[ExpenditureItem] = field(default_factory=list)

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
        met = surf_met(minutes, session.wave_size)
        kcal = activity_kcal(met, weight_kg, minutes)
        expenditure.surf_min += minutes
        expenditure.surf_kcal += kcal
        expenditure.items.append(
            ExpenditureItem(
                kind="surf",
                label=session.spot.name if session.spot else "Surf",
                minutes=minutes,
                met=round(met, 1),
                kcal=kcal,
                detail=WAVE_SIZE_LABELS.get(session.wave_size or ""),
            )
        )

    workouts = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.started_at >= start)
        .where(WorkoutSession.started_at < end)
    )
    workout_rows = workouts.scalars().all()
    patterns = await dominant_patterns(
        db, [w.formula_id for w in workout_rows if w.formula_id]
    )
    for workout in workout_rows:
        minutes = workout.duration_min or 0
        if minutes <= 0:
            continue
        # Le pattern dominant de la formule d'abord ; sa famille en repli. Une
        # séance garde le nom de sa formule même si celle-ci disparaît, et il
        # ne faut pas que la dépense d'une journée passée change ce jour-là.
        pattern = patterns.get(workout.formula_id or -1) or (
            workout.formula_family or ""
        )
        met = WORKOUT_MET.get(pattern, WORKOUT_MET_DEFAULT)
        kcal = activity_kcal(met, weight_kg, minutes)
        expenditure.workout_min += minutes
        expenditure.workout_kcal += kcal
        expenditure.items.append(
            ExpenditureItem(
                kind="workout",
                label=workout.formula_name or "Séance",
                minutes=minutes,
                met=round(met, 1),
                kcal=kcal,
                detail=PATTERN_LABELS.get(pattern),
            )
        )

    # Dans l'ordre où la journée s'est vécue, comme l'écran Jour.
    expenditure.items.sort(key=lambda item: (item.kind != "surf", -item.minutes))
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
