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
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select, update
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
    RecipeItem,
    RecipeNote,
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
    AwayRequest,
    RecipeItemRead,
    RecipeNoteWrite,
    RecipeRead,
    RecipeWrite,
    RegenerateRequest,
    SetRecipeRequest,
    ShoppingLineRead,
    SwapRequest,
    TargetRead,
    WeighInResponse,
)
from app.services.auth_service import get_current_active_user
from app.services.food_units import to_shopping_unit
from app.services.meal_plan import (
    PLANNED_MEALS,
    Candidate,
    PlannedMeal,
    WeekPlan,
    day_share,
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
from app.services.nutrition_seed import (
    ensure_seeded,
    find_food,
    normalize,
    recompute_macros,
)
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


# ── La bibliothèque de recettes ──────────────────────────────────


def _item_read(item: RecipeItem) -> RecipeItemRead:
    """Un ingrédient, traduit dans l'unité où il s'achète et se casse.

    Les grammes restent affichés à côté : la conversion est une moyenne (un œuf
    à 55 g, une courgette à 200 g), et une moyenne qu'on présenterait seule
    passerait pour une mesure.
    """
    quantity = to_shopping_unit(item.label, item.quantity_g)
    return RecipeItemRead(
        label=item.label,
        quantity_g=item.quantity_g,
        food_id=item.food_id,
        unit=quantity.unit,
        quantity=quantity.quantity,
        unit_label=quantity.unit_label,
    )


def _recipe_read(recipe: Recipe, note: Optional[RecipeNote] = None) -> RecipeRead:
    """La recette **et ce que l'utilisateur en pense**, en un seul objet.

    Les deux viennent de tables différentes et c'est voulu (le semis réécrit
    l'une, jamais l'autre), mais à l'écran ils ne font qu'une chose : la fiche
    d'une recette.
    """
    return RecipeRead(
        id=recipe.id,
        slug=recipe.slug,
        name=recipe.name,
        meals=list(recipe.meals or []),
        tags=list(recipe.tags or []),
        servings=recipe.servings,
        prep_min=recipe.prep_min,
        steps=recipe.steps,
        kcal=recipe.kcal,
        protein_g=recipe.protein_g,
        carb_g=recipe.carb_g,
        fat_g=recipe.fat_g,
        items=[_item_read(item) for item in recipe.items],
        source=recipe.source,
        based_on_id=recipe.based_on_id,
        favorite=bool(note.favorite) if note is not None else False,
        note=note.note if note is not None else None,
        cooked_count=note.cooked_count if note is not None else 0,
    )


def _visible_recipes(user_id: int):
    """Le catalogue commun, plus **ses** recettes. Jamais celles d'un autre."""
    return select(Recipe).where(
        or_(Recipe.user_id.is_(None), Recipe.user_id == user_id)
    )


async def _notes_for(
    db: AsyncSession, user_id: int, recipe_ids: Iterable[Optional[int]]
) -> dict[int, RecipeNote]:
    ids = [recipe_id for recipe_id in set(recipe_ids) if recipe_id]
    if not ids:
        return {}
    result = await db.execute(
        select(RecipeNote)
        .where(RecipeNote.user_id == user_id)
        .where(RecipeNote.recipe_id.in_(ids))
    )
    return {note.recipe_id: note for note in result.scalars().all()}


async def _get_visible_recipe(
    db: AsyncSession, user_id: int, recipe_id: int
) -> Recipe:
    result = await db.execute(
        _visible_recipes(user_id).where(Recipe.id == recipe_id)
    )
    recipe = result.scalar_one_or_none()
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recette introuvable"
        )
    return recipe


def _slugify(name: str) -> str:
    """Le slug d'une recette perso — **toujours préfixé `perso-`**.

    Le préfixe n'est pas décoratif : aucun slug du catalogue ne commence par
    `perso-`, donc une recette écrite à la main ne peut pas occuper le slug
    d'une recette que le catalogue ajoutera demain — ce qui ferait échouer le
    semis sur la contrainte d'unicité, au premier accès à l'écran Nutrition.
    """
    key = normalize(name).replace("œ", "oe").replace("'", " ")
    slug = "-".join(part for part in key.replace("-", " ").split() if part)
    return f"perso-{slug[:60]}" if slug else "perso-recette"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    """Un slug libre. Le suffixe numérique n'est pas de la cosmétique : deux
    versions perso de la même recette sont un cas normal, pas une erreur."""
    candidate = base
    suffix = 2
    while True:
        taken = await db.execute(select(Recipe.id).where(Recipe.slug == candidate))
        if taken.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


async def _apply_recipe_write(
    db: AsyncSession, recipe: Recipe, data: RecipeWrite
) -> None:
    """Écrit les champs fournis, puis **recalcule les macros**.

    Les valeurs nutritionnelles ne sont jamais saisies, ici pas plus qu'au
    semis : elles se déduisent des ingrédients et de la table Ciqual. Une
    recette annoncée « à 450 kcal » par son auteur serait une estimation qu'on
    prendrait pour une mesure dès le lendemain.
    """
    values = data.model_dump(exclude_unset=True)
    items = values.pop("items", None)

    for field_name, value in values.items():
        if value is not None:
            setattr(recipe, field_name, value)

    if items is not None:
        # Remplacés en bloc, comme au semis : fusionner ligne à ligne
        # laisserait des ingrédients fantômes après une suppression.
        recipe.items = [
            RecipeItem(
                position=index,
                label=item["label"],
                ciqual_query=item.get("ciqual_query") or item["label"],
                quantity_g=item["quantity_g"],
            )
            for index, item in enumerate(items)
        ]

    await db.flush()

    foods: dict[int, Food] = {}
    for item in recipe.items:
        food = await find_food(db, item.ciqual_query or item.label)
        if food is not None:
            item.food_id = food.id
            foods[food.id] = food
    recompute_macros(recipe, foods)


@router.get("/recipes", response_model=list[RecipeRead])
async def list_recipes(
    meal: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    q: str = Query(default="", max_length=80),
    favorite: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[RecipeRead]:
    """Les recettes semées et les siennes. Sème au premier appel, comme le
    catalogue d'exercices.

    **Les favorites d'abord**, toujours. C'est l'ordre dans lequel on cherche un
    plat de remplacement : d'abord ce qu'on aime, ensuite le reste.
    """
    await ensure_seeded(db)

    result = await db.execute(_visible_recipes(current_user.id).order_by(Recipe.name))
    recipes = list(result.scalars().all())
    notes = await _notes_for(db, current_user.id, [item.id for item in recipes])

    if meal:
        recipes = [item for item in recipes if meal in (item.meals or [])]
    if tag:
        recipes = [item for item in recipes if tag in (item.tags or [])]
    if favorite:
        recipes = [
            item for item in recipes if item.id in notes and notes[item.id].favorite
        ]

    needle = normalize(q)
    if needle:
        recipes = [item for item in recipes if needle in normalize(item.name)]

    recipes.sort(
        key=lambda item: (
            0 if (item.id in notes and notes[item.id].favorite) else 1,
            item.name,
        )
    )
    return [_recipe_read(item, notes.get(item.id)) for item in recipes]


@router.post(
    "/recipes", response_model=RecipeRead, status_code=status.HTTP_201_CREATED
)
async def create_recipe(
    data: RecipeWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecipeRead:
    """Une recette à soi. `source='user'` : **le semis n'y touchera jamais**."""
    if not data.name or not data.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Une recette a besoin d'un nom et d'au moins un ingrédient.",
        )

    recipe = Recipe(
        slug=await _unique_slug(db, _slugify(data.name)),
        name=data.name,
        source="user",
        user_id=current_user.id,
        meals=list(data.meals or ["dinner"]),
        tags=list(data.tags or []),
        servings=data.servings or 1,
        prep_min=data.prep_min if data.prep_min is not None else 15,
        steps=data.steps,
        # La collection est posée **vide à la construction**, avant tout flush :
        # l'assigner sur une ligne déjà persistée ferait charger l'ancienne, et
        # un chargement paresseux en asynchrone lève `MissingGreenlet`.
        items=[],
    )
    db.add(recipe)

    await _apply_recipe_write(db, recipe, RecipeWrite(items=data.items))
    await db.commit()
    await db.refresh(recipe, ["items"])
    return _recipe_read(recipe)


@router.get("/recipes/{recipe_id}", response_model=RecipeRead)
async def read_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecipeRead:
    recipe = await _get_visible_recipe(db, current_user.id, recipe_id)
    notes = await _notes_for(db, current_user.id, [recipe.id])
    return _recipe_read(recipe, notes.get(recipe.id))


@router.patch("/recipes/{recipe_id}", response_model=RecipeRead)
async def update_recipe(
    recipe_id: int,
    data: RecipeWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecipeRead:
    """Modifier une recette — et, si elle vient du catalogue, **la dédoubler**.

    C'est le point délicat du lot. Le semis remplace les ingrédients en bloc sur
    les recettes `catalog`, et il rejoue à chaque fois qu'il trouve des recettes
    sans macros — c'est-à-dire après chaque import Ciqual. Une modification
    écrite directement sur une ligne semée disparaîtrait donc **sans un mot**,
    des semaines plus tard, sans que rien ne permette de comprendre pourquoi.

    Alors on copie : la version modifiée devient une recette `user`, que le
    semis ignore, et qui porte `based_on_id` pour se souvenir d'où elle vient.
    Le menu de la semaine en cours et des semaines à venir la suit — c'est le
    plat qu'on va cuisiner. Les semaines passées gardent l'original : elles
    disent ce qui était prévu à l'époque, et le réécrire serait mentir.
    """
    recipe = await _get_visible_recipe(db, current_user.id, recipe_id)
    forked_from: Optional[int] = None

    if recipe.source != "user":
        original = recipe
        recipe = Recipe(
            slug=await _unique_slug(db, f"perso-{original.slug}"),
            name=original.name,
            source="user",
            user_id=current_user.id,
            based_on_id=original.id,
            meals=list(original.meals or []),
            tags=list(original.tags or []),
            servings=original.servings,
            prep_min=original.prep_min,
            steps=original.steps,
            kcal=original.kcal,
            protein_g=original.protein_g,
            carb_g=original.carb_g,
            fat_g=original.fat_g,
        )
        recipe.items = [
            RecipeItem(
                position=item.position,
                label=item.label,
                ciqual_query=item.ciqual_query,
                food_id=item.food_id,
                quantity_g=item.quantity_g,
            )
            for item in original.items
        ]
        db.add(recipe)
        await db.flush()
        forked_from = original.id

    await _apply_recipe_write(db, recipe, data)

    if forked_from is not None:
        # Le favori et la note suivent la version perso : c'est elle qu'on
        # regarde désormais, et une note restée sur l'original se lirait comme
        # une note perdue.
        moved = await db.execute(
            select(RecipeNote)
            .where(RecipeNote.user_id == current_user.id)
            .where(RecipeNote.recipe_id == forked_from)
        )
        note = moved.scalar_one_or_none()
        if note is not None:
            note.recipe_id = recipe.id

        await _repoint_future_plans(
            db,
            current_user.id,
            forked_from,
            recipe.id,
            since=_monday(datetime.now(_zone(current_user)).date()),
        )

    await db.commit()
    await db.refresh(recipe, ["items"])
    notes = await _notes_for(db, current_user.id, [recipe.id])
    return _recipe_read(recipe, notes.get(recipe.id))


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Supprime une recette **à soi**. Le catalogue ne se supprime pas — il se
    met de côté en ne le mettant jamais au menu.

    Les créneaux qui la servaient redeviennent vides plutôt que de disparaître :
    un menu avec un dîner « à choisir » se corrige, un menu où le jeudi a
    silencieusement perdu sa ligne se relit trois fois avant qu'on comprenne.
    """
    recipe = await _get_visible_recipe(db, current_user.id, recipe_id)
    if recipe.source != "user":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Les recettes du catalogue ne se suppriment pas.",
        )

    await db.execute(
        update(MealPlanItem)
        .where(MealPlanItem.recipe_id == recipe.id)
        .values(recipe_id=None)
    )
    await db.delete(recipe)
    await db.commit()


@router.put("/recipes/{recipe_id}/note", response_model=RecipeRead)
async def set_recipe_note(
    recipe_id: int,
    data: RecipeNoteWrite,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecipeRead:
    """Le favori et la note libre — « sans le piment c'est meilleur ».

    Dans sa propre table : le semis réécrit les recettes, il ne doit jamais
    pouvoir effacer ce qu'on en a dit.
    """
    recipe = await _get_visible_recipe(db, current_user.id, recipe_id)

    existing = await db.execute(
        select(RecipeNote)
        .where(RecipeNote.user_id == current_user.id)
        .where(RecipeNote.recipe_id == recipe.id)
    )
    note = existing.scalar_one_or_none()
    if note is None:
        note = RecipeNote(user_id=current_user.id, recipe_id=recipe.id)
        db.add(note)

    if data.favorite is not None:
        note.favorite = data.favorite
    if data.note is not None:
        # Une note vidée est une note retirée, pas une chaîne vide : on ne
        # garde pas de lignes de texte sans texte.
        note.note = data.note.strip() or None

    await db.commit()
    await db.refresh(note)
    return _recipe_read(recipe, note)


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
        await _mark_cooked(db, current_user.id, recipe.id)

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


# ── Le menu de la semaine ─────────────────────────────────────
#
# Quatorze créneaux, pas vingt-huit : **déjeuner et dîner seulement**
# (`PLANNED_MEALS`). Un petit déjeuner ne se choisit pas le dimanche pour le
# mardi, il se répète ; un en-cas planifié est un en-cas qu'on ne mange pas.
# Les deux continuent de se journaliser, ils ne se prévoient plus.
#
# Chaque créneau a trois états, et le troisième est le plus utile :
# un plat prévu, un créneau vide à remplir, ou **`away`** — pas chez soi. Un
# créneau `away` ne reçoit pas de plat à la génération et **n'entre pas dans la
# liste de courses** : c'est la seule façon de ne pas acheter le poisson d'un
# dîner au restaurant.


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


async def _candidates(db: AsyncSession, user_id: int) -> list[Candidate]:
    """Le vivier du tirage : le catalogue **et** les recettes perso."""
    result = await db.execute(_visible_recipes(user_id))
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


async def _mark_cooked(db: AsyncSession, user_id: int, recipe_id: int) -> None:
    """Une recette journalisée est une recette cuisinée. On compte.

    Le compteur pourrait s'agréger depuis `food_log` à chaque lecture ; une
    requête par recette à l'ouverture de la bibliothèque coûterait plus que la
    colonne. Et à la différence des macros d'une ligne de journal, ce compteur
    n'a **pas** à être figé : il décrit un usage, pas une mesure.
    """
    existing = await db.execute(
        select(RecipeNote)
        .where(RecipeNote.user_id == user_id)
        .where(RecipeNote.recipe_id == recipe_id)
    )
    note = existing.scalar_one_or_none()
    if note is None:
        note = RecipeNote(user_id=user_id, recipe_id=recipe_id, cooked_count=1)
        db.add(note)
    else:
        note.cooked_count += 1


async def _repoint_future_plans(
    db: AsyncSession,
    user_id: int,
    old_recipe_id: int,
    new_recipe_id: int,
    *,
    since: date,
) -> None:
    """Fait suivre une version perso aux menus **à partir de cette semaine**.

    Les semaines passées gardent l'original : elles disent ce qui était prévu à
    l'époque. Réécrire un menu de la semaine dernière parce qu'on a corrigé une
    quantité aujourd'hui serait la même faute que recalculer un bilan
    alimentaire après une mise à jour de Ciqual.
    """
    plans = await db.execute(
        select(MealPlan.id)
        .where(MealPlan.user_id == user_id)
        .where(MealPlan.week_start >= since)
    )
    ids = [row for row in plans.scalars().all()]
    if not ids:
        return
    await db.execute(
        update(MealPlanItem)
        .where(MealPlanItem.plan_id.in_(ids))
        .where(MealPlanItem.recipe_id == old_recipe_id)
        .values(recipe_id=new_recipe_id)
    )


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
        .options(selectinload(MealPlanItem.recipe).selectinload(Recipe.items))
        .order_by(MealPlanItem.day_index, MealPlanItem.meal)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


def _plan_item_read(
    item: MealPlanItem, notes: dict[int, RecipeNote]
) -> MealPlanItemRead:
    return MealPlanItemRead(
        day_index=item.day_index,
        meal=item.meal,
        servings=item.servings,
        status=item.status,
        recipe=(
            None
            if item.recipe is None
            else _recipe_read(item.recipe, notes.get(item.recipe.id))
        ),
    )


async def _plan_response(
    db: AsyncSession, user_id: int, week_start: date, items: list[MealPlanItem]
) -> MealPlanRead:
    """Le menu et sa liste de courses agrégée.

    **Les créneaux `away` sont sautés.** C'est tout l'intérêt de les marquer :
    on ne fait pas les courses pour un repas qu'on prendra ailleurs.
    """
    ingredients: list[tuple[str, float, Optional[str]]] = []
    for item in items:
        if item.status != "planned" or item.recipe is None:
            continue
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

    notes = await _notes_for(
        db, user_id, [item.recipe.id for item in items if item.recipe is not None]
    )

    return MealPlanRead(
        week_start=week_start,
        items=[_plan_item_read(item, notes) for item in items],
        shopping=[
            ShoppingLineRead(
                label=line.label,
                quantity_g=round(line.quantity_g, 1),
                food_group=line.food_group,
                unit=line.unit,
                quantity=line.quantity,
                unit_label=line.unit_label,
            )
            for line in shopping_list(ingredients)
        ],
    )


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
    items = [item for item in week.items if item.day_index == index]
    notes = await _notes_for(
        db, user_id, [item.recipe.id for item in items if item.recipe is not None]
    )
    return [_plan_item_read(item, notes) for item in items]


async def _find_plan(
    db: AsyncSession, user_id: int, week_start: date
) -> Optional[MealPlan]:
    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.user_id == user_id)
        .where(MealPlan.week_start == week_start)
    )
    return result.scalar_one_or_none()


async def _require_plan(
    db: AsyncSession, user_id: int, week_start: date
) -> MealPlan:
    plan = await _find_plan(db, user_id, week_start)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pas de menu pour cette semaine.",
        )
    return plan


async def _get_or_create_plan(
    db: AsyncSession, user_id: int, week_start: date
) -> MealPlan:
    """Le menu de la semaine, créé s'il n'existe pas.

    « Je ne suis pas là jeudi soir » doit pouvoir s'écrire **avant** d'avoir
    généré quoi que ce soit : c'est même le bon ordre, puisque le générateur
    lira ensuite cette contrainte au lieu de proposer un plat pour rien.
    """
    plan = await _find_plan(db, user_id, week_start)
    if plan is None:
        plan = MealPlan(user_id=user_id, week_start=week_start)
        db.add(plan)
        await db.flush()
    return plan


def _check_meal(meal: str) -> None:
    if meal not in PLANNED_MEALS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Repas non planifiable : {meal}. "
                "Le menu ne prévoit que le déjeuner et le dîner."
            ),
        )


async def _slot(
    db: AsyncSession, plan: MealPlan, day_index: int, meal: str, *, create: bool = False
) -> Optional[MealPlanItem]:
    result = await db.execute(
        select(MealPlanItem)
        .where(MealPlanItem.plan_id == plan.id)
        .where(MealPlanItem.day_index == day_index)
        .where(MealPlanItem.meal == meal)
    )
    item = result.scalar_one_or_none()
    if item is None and create:
        item = MealPlanItem(
            plan_id=plan.id, day_index=day_index, meal=meal, servings=1.0
        )
        db.add(item)
        await db.flush()
    return item


async def _week_target(
    db: AsyncSession, current_user: User, zone: ZoneInfo, today: date
) -> Target:
    nutrition = await get_or_create_nutrition_profile(db, current_user.id)
    start, end = _day_bounds(today, zone)
    return await daily_target(
        db,
        current_user.id,
        current_user.profile,
        nutrition,
        today,
        start=start,
        end=end,
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

    plan = await _find_plan(db, current_user.id, week_start)
    if plan is None:
        return MealPlanRead(week_start=week_start)
    return await _plan_response(
        db, current_user.id, plan.week_start, await _plan_items(db, plan.id)
    )


@router.post("/plan", response_model=MealPlanRead)
async def build_plan(
    week: Optional[date] = Query(default=None),
    seed: Optional[int] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MealPlanRead:
    """(Re)génère le menu de la semaine — sept déjeuners, sept dîners.

    Un glouton sous contrainte de macros et de variété — lisible et testable,
    pas une IA (cf. PROJET.md §9). La cible du jour vient du même calcul que
    l'écran : c'est elle qui décide de la taille des repas.

    **Les créneaux `away` survivent à la régénération.** « Tout régénérer » ne
    doit pas effacer le fait qu'on dîne dehors jeudi : c'est une contrainte de
    la semaine, pas une proposition de l'algorithme. Les redéclarer une fois
    par semaine suffirait à ce qu'on cesse de les déclarer.
    """
    await ensure_seeded(db)

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    week_start = _monday(week or today)

    target = await _week_target(db, current_user, zone, today)

    candidates = await _candidates(db, current_user.id)
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Aucune recette en base.",
        )

    plan = await _get_or_create_plan(db, current_user.id, week_start)
    previous = await _plan_items(db, plan.id)
    away = frozenset(
        (item.day_index, item.meal) for item in previous if item.status == "away"
    )

    generated = generate_week(
        candidates,
        kcal_target=target.kcal,
        protein_target=target.protein_g,
        seed=seed,
        skip=away,
    )

    await db.execute(delete(MealPlanItem).where(MealPlanItem.plan_id == plan.id))

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

    for day_index, meal in sorted(away):
        db.add(
            MealPlanItem(
                plan_id=plan.id,
                day_index=day_index,
                meal=meal,
                recipe_id=None,
                status="away",
                servings=1.0,
            )
        )

    await db.commit()
    return await _plan_response(
        db, current_user.id, plan.week_start, await _plan_items(db, plan.id)
    )


async def _pick_for_slot(
    db: AsyncSession,
    current_user: User,
    plan: MealPlan,
    day_index: int,
    meal: str,
    target: Target,
) -> Optional[Candidate]:
    """Un autre plat pour ce créneau, sans toucher au reste de la semaine.

    La cible passée n'est **pas** celle de la journée : c'est la part que le
    menu couvre vraiment (`day_share`), amputée des repas de ce jour-là qu'on
    prend ailleurs. Viser la journée entière ferait proposer, à chaque tap sur
    « un autre plat », un plat plus gros que celui qu'il remplace — et le menu
    dériverait vers le haut à mesure qu'on le corrige.
    """
    candidates = await _candidates(db, current_user.id)
    by_id = {candidate.id: candidate for candidate in candidates}

    items = await _plan_items(db, plan.id)
    current_plan = WeekPlan(
        meals=[
            PlannedMeal(
                day_index=item.day_index,
                meal=item.meal,
                recipe=by_id[item.recipe_id],
                servings=item.servings,
            )
            for item in items
            if item.recipe_id in by_id and item.status == "planned"
        ]
    )

    away = [
        item.meal
        for item in items
        if item.day_index == day_index
        and item.status == "away"
        and item.meal != meal
    ]
    share = day_share(away)

    return regenerate_meal(
        current_plan,
        candidates,
        day_index=day_index,
        meal=meal,
        kcal_target=target.kcal * share,
        protein_target=target.protein_g * share,
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
    _check_meal(data.meal)

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    week_start = _monday(week or today)

    plan = await _require_plan(db, current_user.id, week_start)
    target = await _week_target(db, current_user, zone, today)

    chosen = await _pick_for_slot(
        db, current_user, plan, data.day_index, data.meal, target
    )
    if chosen is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune autre recette pour ce repas.",
        )

    item = await _slot(db, plan, data.day_index, data.meal, create=True)
    assert item is not None
    item.recipe_id = chosen.id
    # Demander un autre plat sur un créneau marqué « pas là », c'est dire qu'on
    # sera là finalement. On ne rend pas un plat invisible.
    item.status = "planned"

    await db.commit()
    return await _plan_response(
        db, current_user.id, plan.week_start, await _plan_items(db, plan.id)
    )


@router.post("/plan/set", response_model=MealPlanRead)
async def set_plan_meal(
    data: SetRecipeRequest,
    week: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MealPlanRead:
    """Pose **cette** recette sur ce créneau. Le tirage propose, on dispose.

    Aucun contrôle que la recette soit étiquetée pour ce repas : si on veut des
    œufs brouillés à dîner, c'est un choix, pas une erreur. Les étiquettes
    servent au générateur, pas à arbitrer ce que quelqu'un a décidé de manger.
    """
    _check_meal(data.meal)

    zone = _zone(current_user)
    week_start = _monday(week or datetime.now(zone).date())

    recipe = await _get_visible_recipe(db, current_user.id, data.recipe_id)
    plan = await _get_or_create_plan(db, current_user.id, week_start)

    item = await _slot(db, plan, data.day_index, data.meal, create=True)
    assert item is not None
    item.recipe_id = recipe.id
    item.servings = data.servings
    item.status = "planned"

    await db.commit()
    return await _plan_response(
        db, current_user.id, plan.week_start, await _plan_items(db, plan.id)
    )


@router.post("/plan/swap", response_model=MealPlanRead)
async def swap_plan_meals(
    data: SwapRequest,
    week: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MealPlanRead:
    """Échange deux créneaux — le plat du mercredi soir passe au vendredi.

    C'est le geste le plus courant sur un menu qu'on suit vraiment : la semaine
    ne se déroule pas comme prévu, et le plat de deux heures tombe le soir où
    on rentre tard. Le déplacer vaut mieux que le régénérer — on l'avait choisi.

    Tout est échangé, **statut compris** : échanger un dîner prévu avec un soir
    où l'on n'est pas là, c'est bien intervertir les deux soirées.
    """
    for slot in (data.a, data.b):
        _check_meal(slot.meal)

    if (data.a.day_index, data.a.meal) == (data.b.day_index, data.b.meal):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Échanger un créneau avec lui-même ne change rien.",
        )

    zone = _zone(current_user)
    week_start = _monday(week or datetime.now(zone).date())
    plan = await _require_plan(db, current_user.id, week_start)

    first = await _slot(db, plan, data.a.day_index, data.a.meal, create=True)
    second = await _slot(db, plan, data.b.day_index, data.b.meal, create=True)
    assert first is not None and second is not None

    first.recipe_id, second.recipe_id = second.recipe_id, first.recipe_id
    first.servings, second.servings = second.servings, first.servings
    first.status, second.status = second.status, first.status

    await db.commit()
    return await _plan_response(
        db, current_user.id, plan.week_start, await _plan_items(db, plan.id)
    )


@router.post("/plan/away", response_model=MealPlanRead)
async def set_plan_away(
    data: AwayRequest,
    week: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MealPlanRead:
    """« Je ne suis pas chez moi » — et donc je ne mange pas ce qui est prévu.

    Trois conséquences, et c'est la troisième qui compte :

    1. le créneau n'affiche plus de plat ;
    2. la prochaine génération ne lui en donnera pas ;
    3. **ses ingrédients sortent de la liste de courses.**

    Le plat d'origine n'est pas effacé : rentrer finalement le remet en place
    d'un tap. Si le créneau a été régénéré entre-temps et n'a plus de plat, on
    en tire un — revenir chez soi ne doit pas laisser un trou.
    """
    _check_meal(data.meal)

    zone = _zone(current_user)
    today = datetime.now(zone).date()
    week_start = _monday(week or today)
    plan = await _get_or_create_plan(db, current_user.id, week_start)

    item = await _slot(db, plan, data.day_index, data.meal, create=True)
    assert item is not None

    if data.away:
        item.status = "away"
    else:
        item.status = "planned"
        if item.recipe_id is None:
            await ensure_seeded(db)
            target = await _week_target(db, current_user, zone, today)
            chosen = await _pick_for_slot(
                db, current_user, plan, data.day_index, data.meal, target
            )
            if chosen is not None:
                item.recipe_id = chosen.id

    await db.commit()
    return await _plan_response(
        db, current_user.id, plan.week_start, await _plan_items(db, plan.id)
    )
