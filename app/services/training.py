"""Training — semis du catalogue, avancement hebdomadaire, proposition du jour.

Trois choses vivent ici, et elles se tiennent :

1. **Le semis.** Objectifs, exercices et formules sont posés en base depuis
   `training_catalog.py` au premier accès. Idempotent : rejouer ne duplique
   rien et n'écrase aucune mesure. Le catalogue évoluera, la base suit.

2. **L'avancement de la semaine**, compté par **famille** de formules : trois
   Réveils différents dans la semaine, c'est trois réveils. Compter par
   variante ferait croire qu'on n'a rien fait à quelqu'un qui alterne, ce qui
   est exactement le contraire de ce qu'on veut encourager.

3. **La proposition du jour.** La formule qui sert l'objectif le plus en
   retard, pondérée par ce qui a déjà été fait cette semaine et par les
   sessions de surf. Trois jours de surf d'affilée → Post-surf ou Réveil,
   jamais Renfo : le corps a déjà eu sa dose, et proposer du renfo ce jour-là
   est le plus sûr moyen de ne plus jamais ouvrir l'onglet.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.models.formula import Formula, FormulaItem
from app.models.objective import Objective
from app.models.surf_session import SurfSession
from app.models.workout import WorkoutSession
from app.services.training_catalog import (
    BUILTIN_TAXONOMY,
    EXERCISES,
    FORMULAS,
    HOUSE_IMAGES,
    OBJECTIVES,
    normalize_name,
)

logger = logging.getLogger(__name__)

# Au-delà, le corps a eu sa dose d'effort : on propose de la récupération, pas
# du renfo. Trois jours d'affilée est le seuil du document design.
SURF_STREAK_FOR_RECOVERY = 3

# Une séance arrêtée avant ce taux d'avancement est **écourtée**, et comptée
# comme telle. Au-delà, on considère la séance faite : s'arrêter au dernier
# étirement d'une souplesse longue n'est pas un abandon.
COMPLETION_RATIO = 0.8


# ── Semis ──────────────────────────────────────────────────────────────────


async def seed_exercises(db: AsyncSession) -> int:
    """Pose la bibliothèque d'exercices. Idempotent sur le `slug`.

    Les lignes existantes sont **mises à jour** sur les champs rédigés ici
    (nom, catégorie, consignes, alias) et **jamais** sur `image_url`, `source`,
    `license` ni `source_url` : ceux-là viennent de l'import des bases
    ouvertes, et un semis ne doit pas effacer ce qu'un import a enrichi.

    **Une exception, et elle est explicite** : les six exercices de
    `HOUSE_IMAGES`, dont l'image n'est pas importée mais choisie ou dessinée
    ici (cf. plus bas). Elle ne s'applique qu'à une ligne sans image, ou dont
    l'image est déjà l'une des nôtres.
    """
    existing = {
        exercise.slug: exercise
        for exercise in (await db.execute(select(Exercise))).scalars().all()
    }

    created = 0
    for entry in EXERCISES:
        exercise = existing.get(entry["slug"])
        if exercise is None:
            exercise = Exercise(slug=entry["slug"], source="builtin", license="CC0-1.0")
            db.add(exercise)
            created += 1
        exercise.name = entry["name"]
        exercise.name_normalized = normalize_name(entry["name"])
        exercise.category = entry["category"]
        exercise.muscle_group = entry.get("muscle_group")
        exercise.instructions = entry.get("instructions")
        exercise.aliases = list(entry.get("aliases") or [])

        # Ces trente exercices sont écrits ici, en français : leur nom **est**
        # leur nom français, et leurs consignes aussi. Rien à traduire.
        exercise.name_fr = entry["name"]
        if exercise.description_fr is None:
            exercise.description_fr = entry.get("instructions")

        # Taxonomie posée à la main (cf. `BUILTIN_TAXONOMY`) : une règle
        # grossière rangerait la fente basse hanche ouverte dans les jambes et
        # la planche avec touche d'épaule dans le gainage statique, et le
        # générateur proposerait autre chose que ce qu'on a écrit.
        taxonomy = BUILTIN_TAXONOMY.get(entry["slug"])
        if taxonomy is not None:
            (
                exercise.group_key,
                exercise.pattern,
                exercise.equipment,
                exercise.difficulty,
                exercise.effort_kind,
                exercise.unilateral,
            ) = taxonomy

        # ── Les images des six exercices maison (14/09) ────────────────────
        #
        # La règle ci-dessus — « un semis n'écrase jamais une image » — vise
        # ce qu'un **import** a trouvé. Celles-ci ne viennent pas d'un import :
        # ce sont des photos libres choisies et vérifiées une à une, et des
        # pictogrammes dessinés dans l'application. Elles appartiennent au
        # catalogue au même titre que les consignes.
        #
        # La condition les protège quand même dans les deux sens : on ne pose
        # l'image que si la ligne n'en a aucune, **ou** si celle qu'elle porte
        # est déjà l'une des nôtres. Le jour où un import trouve enfin une
        # vraie photo de pop-up, elle reste ; et corriger un pictogramme ici se
        # propage au prochain démarrage sans migration.
        house = HOUSE_IMAGES.get(entry["slug"])
        if house is not None and (
            exercise.image_url is None or exercise.source == house["source"]
        ):
            exercise.image_url = house["image_url"]
            exercise.image_author = house["image_author"]
            exercise.license = house["license"]
            exercise.source_url = house["source_url"]
            exercise.source = house["source"]
            # `images` sert l'alternance des deux photos de free-exercise-db.
            # Une image unique n'a rien à y faire : la laisser ferait clignoter
            # la même image contre elle-même.
            exercise.images = None

    await db.commit()
    return created


async def seed_formulas(db: AsyncSession) -> int:
    """Pose les formules et leurs exercices. Idempotent sur le `slug`.

    Les `formula_items` sont **remplacés en bloc** à chaque semis : une formule
    est une composition, pas un agrégat qu'on retouche ligne à ligne, et
    réconcilier position par position coûterait plus cher que de récrire. Les
    séances déjà faites ne bougent pas — elles figent le nom de la formule et
    de chaque exercice précisément pour ça.
    """
    exercises = {
        exercise.slug: exercise
        for exercise in (await db.execute(select(Exercise))).scalars().all()
    }
    existing = {
        formula.slug: formula
        for formula in (await db.execute(select(Formula))).scalars().all()
    }

    created = 0
    for entry in FORMULAS:
        formula = existing.get(entry["slug"])
        is_new = formula is None
        if is_new:
            formula = Formula(slug=entry["slug"])
            created += 1

        formula.name = entry["name"]
        formula.duration_min = entry["duration_min"]
        formula.weekly_target = entry.get("weekly_target", 0)
        formula.principle = entry["principle"]
        formula.objective_slugs = list(entry.get("objective_slugs") or [])
        formula.tags = list(entry.get("tags") or [])
        formula.variant_of = entry.get("variant_of")
        formula.position = entry.get("position", 0)

        if is_new:
            # Ajoutée **après** l'affectation des colonnes : un `flush` sur un
            # objet encore vide part en base avec des `NULL` et tombe sur la
            # contrainte `NOT NULL` de `name`.
            db.add(formula)

        if formula.items:
            # Les anciennes lignes sont **effacées et vidées en base** avant
            # d'écrire les nouvelles : sans ce `flush`, SQLAlchemy émet les
            # INSERT avant les DELETE et tombe sur la contrainte unique
            # `(formula_id, position)` au deuxième semis.
            formula.items.clear()
            await db.flush()

        for position, item in enumerate(entry["items"]):
            exercise = exercises.get(item["exercise"])
            if exercise is None:
                # Une formule qui cite un exercice absent est une erreur de
                # catalogue : on la signale plutôt que de servir une séance
                # trouée.
                logger.error(
                    "Formule %s : exercice inconnu « %s », ligne ignorée",
                    entry["slug"],
                    item["exercise"],
                )
                continue
            formula.items.append(
                FormulaItem(
                    exercise_id=exercise.id,
                    position=position,
                    sets=item["sets"],
                    reps=item["reps"],
                    duration_s=item["duration_s"],
                    tempo=item.get("tempo"),
                    rest_s=item["rest_s"],
                    note=item.get("note"),
                )
            )

    await db.commit()
    return created


async def seed_objectives(db: AsyncSession, user_id: int) -> int:
    """Pose les trois objectifs du document design pour cet utilisateur.

    **Aucune valeur de départ n'est semée** : elle sera la première mesure. Les
    mesures existantes ne sont jamais touchées — un semis rejoué après une mise
    à jour du catalogue ne doit pas effacer six mois de suivi.
    """
    existing = {
        objective.slug: objective
        for objective in (
            await db.execute(
                select(Objective).where(Objective.user_id == user_id)
            )
        )
        .scalars()
        .all()
    }

    created = 0
    for entry in OBJECTIVES:
        objective = existing.get(entry["slug"])
        if objective is None:
            objective = Objective(user_id=user_id, slug=entry["slug"])
            db.add(objective)
            created += 1
        objective.name = entry["name"]
        objective.measure = entry["measure"]
        objective.unit = entry["unit"]
        objective.direction = entry["direction"]
        objective.target_value = entry.get("target_value")
        objective.measure_every_days = entry.get("measure_every_days", 21)
        objective.position = entry.get("position", 0)

    await db.commit()
    return created


async def ensure_training_seeded(db: AsyncSession, user_id: int) -> None:
    """Semis complet, à l'ouverture de l'écran Training.

    Au premier accès, pas au démarrage de l'application : le conteneur Railway
    redémarre à froid plusieurs fois par jour, et faire ce travail à chaque
    démarrage retarderait la première réponse pour rien.
    """
    await seed_exercises(db)
    await seed_formulas(db)
    await seed_objectives(db, user_id)


# ── Avancement ─────────────────────────────────────────────────────────────


def week_bounds(
    today: Optional[date] = None, timezone: str = "Europe/Paris"
) -> tuple[datetime, datetime]:
    """Lundi 0 h → lundi suivant 0 h, en heure locale, rendus en UTC.

    La semaine commence le lundi : « 3 / 4 cette semaine » n'a de sens que si
    tout le monde parle de la même semaine, et une semaine qui démarrerait il y
    a sept jours glisserait tous les jours.
    """
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("Europe/Paris")

    today = today or datetime.now(zone).date()
    monday = today - timedelta(days=today.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=zone)
    return start.astimezone(UTC), (start + timedelta(days=7)).astimezone(UTC)


async def weekly_counts(
    db: AsyncSession,
    user_id: int,
    today: Optional[date] = None,
    timezone: str = "Europe/Paris",
) -> dict[str, int]:
    """Séances faites cette semaine, **par famille de formules**.

    Une séance écourtée compte pour zéro : elle est enregistrée, elle est
    visible dans l'historique, mais elle ne remplit pas l'objectif hebdomadaire.
    Sinon « 3 / 3 » pourrait vouloir dire trois abandons à la deuxième minute.
    """
    start, end = week_bounds(today, timezone)
    result = await db.execute(
        select(
            WorkoutSession.formula_family,
            func.count(WorkoutSession.id),
        )
        .where(WorkoutSession.user_id == user_id)
        .where(WorkoutSession.started_at >= start)
        .where(WorkoutSession.started_at < end)
        .where(WorkoutSession.completed.is_(True))
        .where(WorkoutSession.cut_short.is_(False))
        .group_by(WorkoutSession.formula_family)
    )
    return {family: count for family, count in result.all() if family}


async def surf_streak_days(
    db: AsyncSession,
    user_id: int,
    today: Optional[date] = None,
    timezone: str = "Europe/Paris",
) -> int:
    """Nombre de jours consécutifs avec une session de surf, aujourd'hui inclus.

    Le compteur repart de la veille si rien n'a été fait aujourd'hui : à 7 h du
    matin on n'est pas encore allé à l'eau, et la série d'hier reste la bonne
    information pour décider de la séance du jour.
    """
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("Europe/Paris")

    today = today or datetime.now(zone).date()
    horizon = datetime(
        today.year, today.month, today.day, tzinfo=zone
    ) - timedelta(days=14)

    result = await db.execute(
        select(SurfSession.started_at)
        .where(SurfSession.user_id == user_id)
        .where(SurfSession.deleted_at.is_(None))
        .where(SurfSession.started_at >= horizon.astimezone(UTC))
    )
    days = {
        (
            row if row.tzinfo else row.replace(tzinfo=UTC)
        ).astimezone(zone).date()
        for row in result.scalars().all()
    }
    if not days:
        return 0

    # Le point de départ : aujourd'hui s'il y a eu une session, hier sinon.
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ── Proposition du jour ────────────────────────────────────────────────────


@dataclass
class ObjectiveProgress:
    """L'avancement d'un objectif, de 0 (départ) à 1 (cible)."""

    objective: Objective
    start_value: Optional[float]
    current_value: Optional[float]
    target_value: Optional[float]
    ratio: Optional[float]
    needs_measurement: bool = False

    @property
    def behind(self) -> float:
        """Ce qu'il reste à faire, de 0 à 1. Un objectif sans mesure est le
        plus en retard de tous — c'est d'abord de mesurer qu'il a besoin."""
        if self.ratio is None:
            return 1.0
        return max(0.0, 1.0 - self.ratio)


@dataclass
class Proposal:
    """La séance proposée, et pourquoi."""

    formula: Optional[Formula]
    reason: str
    alternatives: list[Formula] = field(default_factory=list)
    surf_streak: int = 0


def objective_progress(
    objective: Objective, today: Optional[date] = None
) -> ObjectiveProgress:
    """Où en est un objectif, et faut-il le remesurer ?

    Le ratio est calculé **dans le sens de la progression** : « mains-sol » va
    de −14 cm vers 0, donc vers le haut ; un tour de taille irait vers le bas.
    Sans cette bascule, la moitié des jauges liraient un progrès comme un
    recul.

    Sans cible, ou sans départ, il n'y a pas de ratio — et pas de jauge
    inventée pour meubler.
    """
    today = today or date.today()
    start = objective.start_value
    current = objective.current_value
    target = objective.target_value

    ratio: Optional[float] = None
    if start is not None and current is not None and target is not None:
        span = target - start
        if abs(span) < 1e-9:
            # Départ déjà sur la cible : l'objectif est atteint par
            # construction, pas par une division par zéro.
            ratio = 1.0
        else:
            ratio = max(0.0, min(1.0, (current - start) / span))

    last = objective.last_measured_on
    needs = last is None or (today - last).days >= objective.measure_every_days

    return ObjectiveProgress(
        objective=objective,
        start_value=start,
        current_value=current,
        target_value=target,
        ratio=ratio,
        needs_measurement=needs,
    )


def _eligible(formula: Formula, surf_streak: int) -> bool:
    """Cette formule a-t-elle sa place aujourd'hui ?

    Une seule exclusion dure, et elle vient du document design : **trois jours
    de surf d'affilée, pas de renfo**. Le corps a déjà eu sa dose ; proposer du
    renfo ce jour-là est le plus sûr moyen de ne plus jamais ouvrir l'onglet.
    """
    tags = set(formula.tags or [])
    if surf_streak >= SURF_STREAK_FOR_RECOVERY and "strength" in tags:
        return False
    return formula.is_active


def _score_formula(
    formula: Formula,
    behind_by_objective: dict[str, float],
    done_this_week: dict[str, int],
    surf_streak: int,
) -> float:
    """Combien cette formule mérite-t-elle d'être proposée aujourd'hui ?

    Trois termes, dans cet ordre d'importance :

    1. **le retard des objectifs qu'elle sert** — c'est la règle du document
       design, et elle reste la première ;
    2. **ce qui a déjà été fait cette semaine** — une formule à 2/2 tombe très
       bas, une formule à 0/3 remonte. C'est ce qui évite de proposer trois
       fois la même chose parce qu'elle sert le même objectif ;
    3. **la fatigue de mer** — après trois jours à l'eau, la récupération
       passe devant.
    """
    served = formula.objective_slugs or []
    behind = max((behind_by_objective.get(slug, 0.0) for slug in served), default=0.0)

    score = behind

    target = formula.weekly_target
    done = done_this_week.get(formula.family, 0)
    if target > 0:
        remaining = max(0, target - done) / target
        score += 0.8 * remaining
        if done >= target:
            # Objectif de la semaine tenu : elle ne passe plus devant une
            # formule qui n'a pas été faite, sans disparaître pour autant.
            score -= 0.6
    else:
        # Formule « à la demande » (Post-surf) : elle ne concourt pas sur le
        # rythme hebdomadaire, seulement sur le contexte.
        score += 0.15

    tags = set(formula.tags or [])
    if surf_streak >= SURF_STREAK_FOR_RECOVERY and (
        "post_surf" in tags or "morning" in tags
    ):
        score += 1.2

    # À variantes équivalentes, la principale de la famille passe devant.
    if formula.variant_of is None:
        score += 0.05

    return score


async def propose_today(
    db: AsyncSession,
    user_id: int,
    today: Optional[date] = None,
    timezone: str = "Europe/Paris",
) -> Proposal:
    """**Une seule** proposition, remplaçable en un tap.

    Une seule, et c'est le point : l'écran Jour affiche la journée telle
    qu'elle se vit, pas un catalogue. Trois propositions obligeraient à choisir
    à 7 h du matin, ce qui revient à n'en faire aucune. Les alternatives
    existent, derrière un tap.
    """
    formulas = list(
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
    if not formulas:
        return Proposal(formula=None, reason="Aucune formule au catalogue.")

    objectives = list(
        (
            await db.execute(
                select(Objective)
                .where(Objective.user_id == user_id)
                .where(Objective.is_active.is_(True))
                .order_by(Objective.position)
            )
        )
        .scalars()
        .all()
    )
    progress = {
        objective.slug: objective_progress(objective, today)
        for objective in objectives
    }
    behind_by_objective = {slug: item.behind for slug, item in progress.items()}

    done = await weekly_counts(db, user_id, today, timezone)
    streak = await surf_streak_days(db, user_id, today, timezone)

    eligible = [formula for formula in formulas if _eligible(formula, streak)]
    # Tout est exclu (trois jours de surf et rien que du renfo au catalogue) :
    # on préfère proposer quelque chose de discutable que rien du tout.
    candidates = eligible or formulas

    ranked = sorted(
        candidates,
        key=lambda formula: (
            -_score_formula(formula, behind_by_objective, done, streak),
            formula.position,
        ),
    )
    best = ranked[0]

    return Proposal(
        formula=best,
        reason=_explain(best, progress, done, streak),
        # Une alternative par famille : le remplacement en un tap doit proposer
        # autre chose, pas une variante de la même séance.
        alternatives=_one_per_family(ranked[1:], exclude=best.family)[:3],
        surf_streak=streak,
    )


def _one_per_family(
    formulas: Sequence[Formula], exclude: Optional[str] = None
) -> list[Formula]:
    seen: set[str] = {exclude} if exclude else set()
    out: list[Formula] = []
    for formula in formulas:
        if formula.family in seen:
            continue
        seen.add(formula.family)
        out.append(formula)
    return out


def _explain(
    formula: Formula,
    progress: dict[str, ObjectiveProgress],
    done: dict[str, int],
    streak: int,
) -> str:
    """Une phrase, en français, qui dit pourquoi celle-ci et pas une autre.

    Pas de la décoration : une proposition qu'on ne comprend pas se remplace au
    hasard, et on finit par ne plus la lire.
    """
    if streak >= SURF_STREAK_FOR_RECOVERY and "strength" not in set(
        formula.tags or []
    ):
        return f"{streak} jours de surf d'affilée — récupération plutôt que renfo."

    served = formula.objective_slugs or []
    if served:
        worst = max(
            (progress[slug] for slug in served if slug in progress),
            key=lambda item: item.behind,
            default=None,
        )
        if worst is not None:
            if worst.ratio is None:
                return (
                    f"{worst.objective.name} n'a pas encore de mesure — "
                    "c'est l'objectif le plus en retard par défaut."
                )
            if worst.behind > 0.05:
                return (
                    f"{worst.objective.name} est l'objectif le plus en retard "
                    f"({round(worst.ratio * 100)} % du chemin)."
                )

    target = formula.weekly_target
    if target > 0:
        return f"{done.get(formula.family, 0)} / {target} cette semaine."
    return "Séance à la demande."
