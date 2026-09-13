"""Semis des recettes, et appariement avec la table Ciqual.

Comme le catalogue d'exercices du lot 4 : le **contenu** est semé par
l'application, pas par une migration. Il évoluera — une quantité corrigée, une
recette ajoutée — et on n'écrit pas une migration par cuillère de riz.

Le semis est **idempotent sur le slug** et il tourne au premier accès à l'écran
Nutrition. Il fait deux choses :

1. Il crée ou met à jour les recettes et leurs ingrédients ;
2. Il **rapproche** chaque ingrédient de la table Ciqual, s'il y en a une, et
   recalcule les valeurs nutritionnelles de la recette.

Le second point est rejoué à chaque semis, et c'est voulu : les recettes
existent avant l'import Ciqual, sans macros, et se complètent toutes seules le
jour où la table arrive.
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import Food, Recipe, RecipeItem
from app.services.recipes_catalog import ALL_RECIPES, RecipeSpec

logger = logging.getLogger(__name__)


def normalize(value: str) -> str:
    """Même normalisation que l'import Ciqual : minuscules, sans accents."""
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(stripped.lower().split())


async def find_food(db: AsyncSession, query: str) -> Optional[Food]:
    """L'aliment Ciqual qui correspond le mieux à un nom d'ingrédient.

    Trois passes, de la plus stricte à la plus lâche : égalité, début de nom,
    puis contenu. On prend **le nom le plus court** parmi les candidats, ce qui
    est une heuristique grossière et assumée — dans Ciqual, « Riz blanc cuit »
    est plus générique que « Riz blanc cuit, étuvé, à l'eau salée », et c'est le
    générique qu'on veut pour une recette.
    """
    needle = normalize(query)
    if not needle:
        return None

    for condition in (
        Food.name_normalized == needle,
        Food.name_normalized.like(f"{needle}%"),
        Food.name_normalized.like(f"%{needle}%"),
    ):
        result = await db.execute(
            select(Food)
            .where(condition)
            .order_by(func.length(Food.name_normalized))
            .limit(1)
        )
        food = result.scalar_one_or_none()
        if food is not None:
            return food
    return None


def recompute_macros(recipe: Recipe, foods: dict[int, Food]) -> None:
    """Recalcule les valeurs **par portion** depuis les ingrédients.

    Jamais saisies : une recette annoncée « à 450 kcal » serait une estimation
    qu'on prendrait pour une mesure dès le lendemain.

    Tout reste nul tant qu'**aucun** ingrédient n'est apparié. En revanche, un
    appariement partiel donne un total partiel, et c'est le bon compromis : une
    recette dont on connaît le riz et le poulet mais pas l'huile d'olive est
    déjà utilisable par le générateur, à dix kilocalories près.
    """
    totals = {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
    matched = False

    for item in recipe.items:
        food = foods.get(item.food_id) if item.food_id else None
        if food is None or food.kcal_100g is None:
            continue
        matched = True
        factor = item.quantity_g / 100.0
        totals["kcal"] += (food.kcal_100g or 0.0) * factor
        totals["protein_g"] += (food.protein_100g or 0.0) * factor
        totals["carb_g"] += (food.carb_100g or 0.0) * factor
        totals["fat_g"] += (food.fat_100g or 0.0) * factor

    if not matched:
        recipe.kcal = None
        recipe.protein_g = None
        recipe.carb_g = None
        recipe.fat_g = None
        return

    servings = max(1, recipe.servings)
    recipe.kcal = round(totals["kcal"] / servings, 1)
    recipe.protein_g = round(totals["protein_g"] / servings, 1)
    recipe.carb_g = round(totals["carb_g"] / servings, 1)
    recipe.fat_g = round(totals["fat_g"] / servings, 1)


async def _upsert_recipe(db: AsyncSession, spec: RecipeSpec) -> Recipe:
    result = await db.execute(select(Recipe).where(Recipe.slug == spec.slug))
    recipe = result.scalar_one_or_none()

    if recipe is None:
        recipe = Recipe(slug=spec.slug)
        db.add(recipe)

    recipe.name = spec.name
    recipe.meals = list(spec.meals)
    recipe.tags = list(spec.tags)
    recipe.servings = spec.servings
    recipe.prep_min = spec.prep_min
    recipe.steps = spec.steps

    # Les ingrédients sont remplacés en bloc : une recette corrigée dans le
    # catalogue doit l'être en base, et fusionner ligne à ligne laisserait des
    # ingrédients fantômes après une suppression.
    recipe.items = [
        RecipeItem(
            position=index,
            label=ingredient.label,
            ciqual_query=ingredient.ciqual_query,
            quantity_g=ingredient.quantity_g,
        )
        for index, ingredient in enumerate(spec.ingredients)
    ]
    return recipe


async def seed_recipes(db: AsyncSession) -> dict[str, int]:
    """Sème les recettes et les rapproche de Ciqual. Idempotent."""
    matched = 0
    total_items = 0

    for spec in ALL_RECIPES:
        recipe = await _upsert_recipe(db, spec)
        await db.flush()

        foods: dict[int, Food] = {}
        for item in recipe.items:
            total_items += 1
            food = await find_food(db, item.ciqual_query or item.label)
            if food is not None:
                item.food_id = food.id
                foods[food.id] = food
                matched += 1

        recompute_macros(recipe, foods)

    await db.commit()

    counts = {
        "recipes": len(ALL_RECIPES),
        "items": total_items,
        "matched": matched,
    }
    logger.info(
        "Recettes semées : %d, ingrédients appariés %d/%d",
        counts["recipes"],
        matched,
        total_items,
    )
    return counts


async def ensure_seeded(db: AsyncSession) -> None:
    """Sème au premier accès à l'écran, comme le catalogue d'exercices.

    Le re-semis est également déclenché quand des recettes existent **sans
    macros** alors que la table Ciqual, elle, est remplie : c'est exactement la
    situation d'après-import, et il n'y a aucune raison d'obliger à lancer un
    script pour la résoudre.
    """
    recipes = (
        await db.execute(select(func.count()).select_from(Recipe))
    ).scalar_one()
    if recipes == 0:
        await seed_recipes(db)
        return

    foods = (await db.execute(select(func.count()).select_from(Food))).scalar_one()
    if foods == 0:
        return

    unpriced = (
        await db.execute(
            select(func.count()).select_from(Recipe).where(Recipe.kcal.is_(None))
        )
    ).scalar_one()
    if unpriced:
        logger.info(
            "%d recettes sans valeurs alors que Ciqual est présent : re-semis",
            unpriced,
        )
        await seed_recipes(db)
