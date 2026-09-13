"""Nutrition — cible du jour, journal, menu de la semaine, pesée.

⚠️ **Les routes fixes sont déclarées AVANT les routes paramétrées**
(cf. CLAUDE.md) : `/nutrition/foods` doit précéder `/nutrition/{…}`.

L'écran Nutrition tient dans **un seul appel** (`GET /nutrition/day`) : la
cible, le journal, les totaux et le menu du jour. Trois requêtes coûteraient
trois allers-retours sur un écran qu'on ouvre quatre fois par jour.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.nutrition import (
    BodyMetric,
    Food,
    FoodLog,
    MealPlan,
    MealPlanItem,
    Recipe,
)
from app.models.user import User
from app.schemas.nutrition import (
    BodyMetricRead,
    BodyMetricWrite,
    CalibrationRead,
    ExpenditureRead,
    FoodHit,
    FoodLogCreate,
    FoodLogRead,
    FoodRead,
    MacroTotals,
    MealPlanItemRead,
    MealPlanRead,
    NutritionDay,
    NutritionProfileRead,
    NutritionProfileUpdate,
    RecipeRead,
    RegenerateRequest,
    ShoppingLineRead,
    TargetRead,
    WeighInResponse,
)
from app.services.auth_service import get_current_active_user
from app.services.meal_plan import (
    MEALS,
    Candidate,
    PlannedMeal,
    WeekPlan,
    generate_week,
    regenerate_meal,
    shopping_list,
)
from app.services.nutrition import (
    Target,
    daily_target,
    get_or_create_nutrition_profile,
    recalibrate,
)
from app.services.nutrition_seed import ensure_seeded, normalize
from app.services.openfoodfacts import lookup_barcode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nutrition", tags=["nutrition"])

# Les vingt aliments les plus fréquents passent en tête de la recherche. Vingt
# et pas cinq : à raison de trois repas par jour, la queue est plus longue
# qu'on ne croit, et c'est elle qui décide si un repas tient en vingt secondes.
FREQUENT_LIMIT = 20


def _zone(user: User) -> ZoneInfo:
    name = user.profile.timezone if user.profile else "Europe/Paris"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Paris")


def _day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Les bornes UTC d'une journée locale. Un repas de 23 h 30 est de ce jour."""
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def _target_read(target: Target, weight_kg: Optional[float]) -> TargetRead:
    return TargetRead(
        kcal=target.kcal,
        protein_g=target.protein_g,
        carb_g=target.carb_g,
        fat_g=target.fat_g,
        protein_g_per_kg=(
            None
            if not weight_kg
            else round(target.protein_g / weight_kg, 2)
        ),
        bmr=target.bmr,
        base_kcal=target.base_kcal,
        goal_kcal=target.goal_kcal,
        calibration_kcal=target.calibration_kcal,
        expenditure=ExpenditureRead(
            surf_min=target.expenditure.surf_min,
            surf_kcal=round(target.expenditure.surf_kcal, 1),
            workout_min=target.expenditure.workout_min,
            workout_kcal=round(target.expenditure.workout_kcal, 1),
            total_kcal=round(target.expenditure.total_kcal, 1),
        ),
        estimated=target.estimated,
        reasons=target.reasons,
    )


# ── Routes fixes ───────────────────────────────────────────────────────────


@router.get("/foods", response_model=list[FoodHit])
async def search_foods(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=25, gt=0, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[FoodHit]:
    """Recherche d'aliment, **les plus fréquents en tête**.

    Sans recherche, on rend directement les vingt aliments les plus journalisés
    : c'est l'écran qui s'ouvre, et neuf fois sur dix ce qu'on cherche y est
    déjà. C'est ce qui fait tenir un repas en vingt secondes.

    Les spots ont appris la même leçon au lot 1 ter : chercher ne doit rien
    coûter, et la liste par défaut ne doit pas être vide.
    """
    frequent = await db.execute(
        select(FoodLog.food_id, func.count().label("uses"))
        .where(FoodLog.user_id == current_user.id)
        .where(FoodLog.food_id.is_not(None))
        .group_by(FoodLog.food_id)
        .order_by(func.count().desc())
        .limit(FREQUENT_LIMIT)
    )
    uses = {food_id: count for food_id, count in frequent.all()}

    needle = normalize(q)
    if not needle:
        if not uses:
            return []
        result = await db.execute(select(Food).where(Food.id.in_(list(uses))))
        found = list(result.scalars().all())
        found.sort(key=lambda food: -uses.get(food.id, 0))
        return [
            FoodHit(
                **FoodRead.model_validate(food).model_dump(),
                recent_count=uses.get(food.id, 0),
            )
            for food in found
        ]

    result = await db.execute(
        select(Food)
        .where(Food.name_normalized.like(f"%{needle}%"))
        .limit(limit * 4)
    )

    hits = []
    for food in result.scalars().all():
        # Classement grossier, et il suffit : ce qu'on mange souvent d'abord,
        # puis ce dont le nom commence par la recherche, puis le reste.
        rank = (
            -uses.get(food.id, 0),
            0 if food.name_normalized.startswith(needle) else 1,
            len(food.name),
        )
        hits.append((rank, food))

    hits.sort(key=lambda item: item[0])
    return [
        FoodHit(
            **FoodRead.model_validate(food).model_dump(),
            recent_count=uses.get(food.id, 0),
        )
        for _, food in hits[:limit]
    ]


@router.get("/barcode/{barcode}", response_model=FoodRead)
async def scan_barcode(
    barcode: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FoodRead:
    """Le produit derrière un code-barres — Open Food Facts, mis en cache.

    Le cache n'est pas une optimisation : on scanne dans une cuisine où le wifi
    ne passe pas, et le même paquet revient toutes les semaines.
    """
    food = await lookup_barcode(db, barcode)
    if food is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produit inconnu. Cherche-le par son nom.",
        )
    return FoodRead.model_validate(food)


@router.get("/recipes", response_model=list[RecipeRead])
async def list_recipes(
    meal: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[RecipeRead]:
    """Les recettes semées. Sème au premier appel, comme le catalogue d'exercices."""
    await ensure_seeded(db)

    result = await db.execute(select(Recipe).order_by(Recipe.name))
    recipes = list(result.scalars().all())

    if meal:
        recipes = [item for item in recipes if meal in (item.meals or [])]
    if tag:
        recipes = [item for item in recipes if tag in (item.tags or [])]

    return [RecipeRead.model_validate(item) for item in recipes]


@router.get("/day", response_model=NutritionDay)
async def read_day(
    day: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NutritionDay:
    """Tout l'écran Nutrition pour une journée, en un seul aller-retour."""
    zone = _zone(current_user)
    target_day = day or datetime.now(zone).date()
    start, end = _day_bounds(target_day, zone)

    nutrition = await get_or_create_nutrition_profile(db, current_user.id)
    target = await daily_target(
        db,
        current_user.id,
        current_user.profile,
        nutrition,
        target_day,
        start=start,
        end=end,
    )

    entries = await db.execute(
        select(FoodLog)
        .where(FoodLog.user_id == current_user.id)
        .where(FoodLog.day == target_day)
        .order_by(FoodLog.created_at)
    )
    rows = list(entries.scalars().all())

    totals = MacroTotals()
    for row in rows:
        totals.kcal += row.kcal or 0.0
        totals.protein_g += row.protein_g or 0.0
        totals.carb_g += row.carb_g or 0.0
        totals.fat_g += row.fat_g or 0.0
        totals.fiber_g += row.fiber_g or 0.0
    for field_name in ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g"):
        setattr(totals, field_name, round(getattr(totals, field_name), 1))

    planned = await _planned_for_day(db, current_user.id, target_day)

    from app.services.nutrition import latest_weight

    weight = await latest_weight(db, current_user.id, target_day)
    if weight is None and current_user.profile:
        weight = current_user.profile.weight_kg

    return NutritionDay(
        day=target_day,
        target=_target_read(target, weight),
        totals=totals,
        entries=[FoodLogRead.model_validate(row) for row in rows],
        planned=planned,
    )


@router.post("/log", response_model=FoodLogRead, status_code=status.HTTP_201_CREATED)
async def add_log_entry(
    data: FoodLogCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FoodLogRead:
    """Ajoute une ligne au journal, **valeurs figées à la saisie**.

    Elles pourraient se recalculer depuis `food_id`, et c'est exactement ce
    qu'on ne veut pas : le jour où Ciqual change de version ou qu'une fiche
    Open Food Facts est corrigée, un bilan de la semaine dernière ne doit pas
    changer tout seul.
    """
    zone = _zone(current_user)
    day = data.day or datetime.now(zone).date()

    if (data.food_id is None) == (data.recipe_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Un aliment ou une recette, et un seul des deux.",
        )

    entry = FoodLog(user_id=current_user.id, day=day, meal=data.meal)

    if data.food_id is not None:
        food = await db.get(Food, data.food_id)
        if food is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Aliment introuvable"
            )
        factor = data.quantity_g / 100.0
        entry.food_id = food.id
        entry.label = data.label or food.name
        entry.quantity_g = data.quantity_g
        entry.kcal = _scaled(food.kcal_100g, factor)
        entry.protein_g = _scaled(food.protein_100g, factor)
        entry.carb_g = _scaled(food.carb_100g, factor)
        entry.fat_g = _scaled(food.fat_100g, factor)
        entry.fiber_g = _scaled(food.fiber_100g, factor)
    else:
        recipe = await db.get(Recipe, data.recipe_id)
        if recipe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Recette introuvable"
            )
        entry.recipe_id = recipe.id
        entry.label = data.label or recipe.name
        # Une recette n'a pas de masse : sa quantité est un nombre de parts.
        # On stocke la masse totale de ses ingrédients pour que la colonne
        # garde un sens, mais c'est `servings` qui multiplie les macros.
        entry.quantity_g = sum(item.quantity_g for item in recipe.items) * data.servings
        entry.kcal = _scaled(recipe.kcal, data.servings)
        entry.protein_g = _scaled(recipe.protein_g, data.servings)
        entry.carb_g = _scaled(recipe.carb_g, data.servings)
        entry.fat_g = _scaled(recipe.fat_g, data.servings)

    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return FoodLogRead.model_validate(entry)


def _scaled(value: Optional[float], factor: float) -> Optional[float]:
    """Une valeur pour 100 g mise à l'échelle. `None` reste `None`.

    Un zéro se lirait « cet aliment n'a pas de protéines » ; une absence dit
    « on ne sait pas », et c'est différent.
    """
    return None if value is None else round(value * factor, 1)


@router.delete("/log/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log_entry(
    entry_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Retire une ligne. Pas de corbeille : un repas mal saisi n'a pas de valeur
    d'apprentissage à protéger, contrairement à une session."""
    entry = await db.get(FoodLog, entry_id)
    if entry is None or entry.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ligne introuvable"
        )
    await db.delete(entry)
    await db.commit()


@router.get("/profile", response_model=NutritionProfileRead)
async def read_nutrition_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NutritionProfileRead:
    return NutritionProfileRead.model_validate(
        await get_or_create_nutrition_profile(db, current_user.id)
    )


@router.put("/profile", response_model=NutritionProfileRead)
async def update_nutrition_profile(
    data: NutritionProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> NutritionProfileRead:
    """Objectif, activité, macros — et l'âge et le sexe, dont Mifflin a besoin."""
    nutrition = await get_or_create_nutrition_profile(db, current_user.id)
    values = data.model_dump(exclude_unset=True)

    if "goal" in values and values["goal"] not in {"maintain", "cut", "bulk"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Objectif inconnu : maintain, cut ou bulk.",
        )
    if "sex" in values and values["sex"] not in {None, "male", "female"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Sexe inconnu : male, female, ou rien.",
        )

    # Ces trois-là vivent sur le profil général, pas sur celui de nutrition :
    # l'âge et la taille servent aussi ailleurs, et les dupliquer garantirait
    # qu'ils divergent.
    for field_name in ("birth_date", "sex", "height_m"):
        if field_name in values and current_user.profile is not None:
            setattr(current_user.profile, field_name, values.pop(field_name))
        else:
            values.pop(field_name, None)

    for field_name, value in values.items():
        setattr(nutrition, field_name, value)

    await db.commit()
    await db.refresh(nutrition)
    return NutritionProfileRead.model_validate(nutrition)


@router.get("/weight", response_model=list[BodyMetricRead])
async def list_weigh_ins(
    limit: int = Query(default=52, gt=0, le=400),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[BodyMetricRead]:
    result = await db.execute(
        select(BodyMetric)
        .where(BodyMetric.user_id == current_user.id)
        .order_by(BodyMetric.day.desc())
        .limit(limit)
    )
    return [BodyMetricRead.model_validate(row) for row in result.scalars().all()]


@router.post("/weight", response_model=WeighInResponse)
async def add_weigh_in(
    data: BodyMetricWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> WeighInResponse:
    """La pesée — et la recalibration qu'elle déclenche.

    Une pesée par jour : se repeser le même jour remplace, comme une mesure
    d'objectif au lot 4. La recalibration, elle, ne fait rien la plupart du
    temps et le dit : corriger toutes les semaines transformerait le bruit de
    la balance en oscillation de la cible.
    """
    zone = _zone(current_user)
    day = data.day or datetime.now(zone).date()

    existing = await db.execute(
        select(BodyMetric)
        .where(BodyMetric.user_id == current_user.id)
        .where(BodyMetric.day == day)
    )
    metric = existing.scalar_one_or_none()
    if metric is None:
        metric = BodyMetric(user_id=current_user.id, day=day)
        db.add(metric)

    for field_name in ("weight_kg", "waist_cm", "note"):
        value = getattr(data, field_name)
        if value is not None:
            setattr(metric, field_name, value)

    await db.commit()
    await db.refresh(metric)

    nutrition = await get_or_create_nutrition_profile(db, current_user.id)
    logged = await _logged_days(db, current_user.id)
    calibration = await recalibrate(
        db, current_user.id, nutrition, today=day, logged_days=logged
    )

    return WeighInResponse(
        metric=BodyMetricRead.model_validate(metric),
        calibration=CalibrationRead(**calibration.__dict__),
    )


async def _logged_days(db: AsyncSession, user_id: int, days: int = 28) -> int:
    """Nombre de journées distinctes journalisées sur la fenêtre de calibration.

    Sert de garde-fou : en dessous de la moitié, l'écart de poids mesure ce
    qui n'a pas été noté, pas ce qui a été mangé.
    """
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(func.count(func.distinct(FoodLog.day)))
        .where(FoodLog.user_id == user_id)
        .where(FoodLog.day >= since)
    )
    return int(result.scalar_one() or 0)


# ── Le menu de la semaine ──────────────────────────────────────────────────


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


async def _candidates(db: AsyncSession) -> list[Candidate]:
    result = await db.execute(select(Recipe))
    return [
        Candidate(
            id=recipe.id,
            slug=recipe.slug,
            name=recipe.name,
            meals=tuple(recipe.meals or ()),
            tags=tuple(recipe.tags or ()),
            prep_min=recipe.prep_min,
            kcal=recipe.kcal,
            protein_g=recipe.protein_g,
            carb_g=recipe.carb_g,
            fat_g=recipe.fat_g,
        )
        for recipe in result.scalars().all()
    ]


async def _planned_for_day(
    db: AsyncSession, user_id: int, day: date
) -> list[MealPlanItemRead]:
    plan = await db.execute(
        select(MealPlan)
        .where(MealPlan.user_id == user_id)
        .where(MealPlan.week_start == _monday(day))
    )
    week = plan.scalar_one_or_none()
    if week is None:
        return []
    index = day.weekday()
    return [
        MealPlanItemRead.model_validate(item)
        for item in week.items
        if item.day_index == index
    ]


async def _plan_items(db: AsyncSession, plan_id: int) -> list[MealPlanItem]:
    """Les repas d'un menu, **relus depuis la base**, recettes comprises.

    Deux pièges se croisent ici, et il faut les deux pour que ça marche.

    1. `refresh()` expire les relations sans les recharger : les relire
       déclencherait un chargement paresseux, interdit en asynchrone
       (`MissingGreenlet`). D'où les `selectinload` explicites.
    2. **La session tourne en `expire_on_commit=False`** (`db/database.py`).
       Une requête qui retombe sur des objets déjà en mémoire les rend tels
       qu'ils sont, sans relire la base : après un changement de `recipe_id`,
       la relation `recipe` pointerait encore sur **l'ancienne** recette, et
       l'écran afficherait le plat qu'on vient de remplacer. `populate_existing`
       force la mise à jour des instances déjà chargées, et c'est exactement le
       remède prévu pour ce cas.
    """
    result = await db.execute(
        select(MealPlanItem)
        .where(MealPlanItem.plan_id == plan_id)
        .options(
            selectinload(MealPlanItem.recipe).selectinload(Recipe.items)
        )
        .order_by(MealPlanItem.day_index, MealPlanItem.meal)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def _plan_response(
    db: AsyncSession, week_start: date, items: list[MealPlanItem]
) -> MealPlanRead:
    """Le menu et sa liste de courses agrégée."""
    ingredients: list[tuple[str, float, Optional[str]]] = []
    for item in items:
        for ingredient in item.recipe.items:
            food = (
                await db.get(Food, ingredient.food_id)
                if ingredient.food_id
                else None
            )
            ingredients.append(
                (
                    ingredient.label,
                    ingredient.quantity_g * item.servings,
                    food.food_group if food else None,
                )
            )

    return MealPlanRead(
        week_start=week_start,
        items=[MealPlanItemRead.model_validate(item) for item in items],
        shopping=[
            ShoppingLineRead(
                label=line.label,
                quantity_g=round(line.quantity_g, 1),
                food_group=line.food_group,
            )
            for line in shopping_list(ingredients)
        ],
    )


@router.get("/plan", response_model=MealPlanRead)
async def read_plan(
    week: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MealPlanRead:
    """Le menu de la semaine. Vide tant qu'il n'a pas été généré."""
    zone = _zone(current_user)
    week_start = _monday(week or datetime.now(zone).date())

    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.user_id == current_user.id)
        .where(MealPlan.week_start == week_start)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        return MealPlanRead(week_start=week_start)
    return await _plan_response(
        db, plan.week_start, await _plan_items(db, plan.id)
    )


@router.post("/plan", response_model=MealPlanRead)
async def build_plan(
    week: Optional[date] = Query(default=None),
    seed: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MealPlanRead:
    """(Re)génère le menu de la semaine.

    Un glouton sous contrainte de macros et de variété — lisible et testable,
    pas une IA (cf. PROJET.md §9). La cible du jour vient du même calcul que
    l'écran : c'est elle qui décide de la taille des repas.
    """
    await ensure_seeded(db)

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    week_start = _monday(week or today)

    nutrition = await get_or_create_nutrition_profile(db, current_user.id)
    start, end = _day_bounds(today, zone)
    target = await daily_target(
        db,
        current_user.id,
        current_user.profile,
        nutrition,
        today,
        start=start,
        end=end,
    )

    candidates = await _candidates(db)
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Aucune recette en base.",
        )

    generated = generate_week(
        candidates,
        kcal_target=target.kcal,
        protein_target=target.protein_g,
        seed=seed,
    )

    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.user_id == current_user.id)
        .where(MealPlan.week_start == week_start)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        plan = MealPlan(user_id=current_user.id, week_start=week_start)
        db.add(plan)
        await db.flush()
    else:
        await db.execute(
            delete(MealPlanItem).where(MealPlanItem.plan_id == plan.id)
        )

    for item in generated.meals:
        db.add(
            MealPlanItem(
                plan_id=plan.id,
                day_index=item.day_index,
                meal=item.meal,
                recipe_id=item.recipe.id,
                servings=item.servings,
            )
        )

    await db.commit()
    return await _plan_response(
        db, plan.week_start, await _plan_items(db, plan.id)
    )


@router.post("/plan/regenerate", response_model=MealPlanRead)
async def regenerate_plan_meal(
    data: RegenerateRequest,
    week: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MealPlanRead:
    """Remplace **un** repas, sans toucher au reste de la semaine.

    Le geste qui compte : un menu dont on ne peut changer qu'un plat se garde,
    un menu qu'il faut régénérer en entier pour corriger un dîner se jette.
    """
    if data.meal not in MEALS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Repas inconnu : {data.meal}",
        )

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    week_start = _monday(week or today)

    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.user_id == current_user.id)
        .where(MealPlan.week_start == week_start)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pas de menu pour cette semaine.",
        )

    nutrition = await get_or_create_nutrition_profile(db, current_user.id)
    start, end = _day_bounds(today, zone)
    target = await daily_target(
        db,
        current_user.id,
        current_user.profile,
        nutrition,
        today,
        start=start,
        end=end,
    )

    candidates = await _candidates(db)
    by_id = {candidate.id: candidate for candidate in candidates}

    current_plan = WeekPlan(
        meals=[
            PlannedMeal(
                day_index=item.day_index,
                meal=item.meal,
                recipe=by_id[item.recipe_id],
                servings=item.servings,
            )
            for item in plan.items
            if item.recipe_id in by_id
        ]
    )

    chosen = regenerate_meal(
        current_plan,
        candidates,
        day_index=data.day_index,
        meal=data.meal,
        kcal_target=target.kcal,
        protein_target=target.protein_g,
    )
    if chosen is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune autre recette pour ce repas.",
        )

    existing = next(
        (
            item
            for item in plan.items
            if item.day_index == data.day_index and item.meal == data.meal
        ),
        None,
    )
    if existing is None:
        db.add(
            MealPlanItem(
                plan_id=plan.id,
                day_index=data.day_index,
                meal=data.meal,
                recipe_id=chosen.id,
                servings=1.0,
            )
        )
    else:
        existing.recipe_id = chosen.id

    await db.commit()
    return await _plan_response(
        db, plan.week_start, await _plan_items(db, plan.id)
    )
