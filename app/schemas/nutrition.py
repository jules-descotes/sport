from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UtcDatetime


class FoodRead(BaseModel):
    """Un aliment — Ciqual ou Open Food Facts. Valeurs **pour 100 g**."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    food_group: Optional[str] = None
    brand: Optional[str] = None
    barcode: Optional[str] = None
    source: str
    kcal_100g: Optional[float] = None
    protein_100g: Optional[float] = None
    carb_100g: Optional[float] = None
    fat_100g: Optional[float] = None
    fiber_100g: Optional[float] = None


class FoodHit(FoodRead):
    """Un résultat de recherche. `recent_count` porte les vingt aliments les
    plus fréquents en tête de liste — c'est ce qui fait tenir un repas en
    vingt secondes."""

    recent_count: int = 0


class FoodLogCreate(BaseModel):
    """Une ligne du journal. Un aliment **ou** une recette, jamais les deux."""

    day: Optional[date] = None
    meal: str = "lunch"
    food_id: Optional[int] = None
    recipe_id: Optional[int] = None
    # Grammes pour un aliment, **portions** pour une recette : une recette n'a
    # pas de masse, elle a un nombre de parts.
    quantity_g: float = Field(default=100.0, gt=0, le=5000)
    servings: float = Field(default=1.0, gt=0, le=10)
    label: Optional[str] = Field(default=None, max_length=160)


class FoodLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    meal: str
    food_id: Optional[int] = None
    recipe_id: Optional[int] = None
    label: str
    quantity_g: float
    # Figées à la saisie : un bilan de la semaine dernière ne doit pas changer
    # parce qu'une base a été mise à jour.
    kcal: Optional[float] = None
    protein_g: Optional[float] = None
    carb_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    created_at: UtcDatetime


class MacroTotals(BaseModel):
    kcal: float = 0.0
    protein_g: float = 0.0
    carb_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0


class ExpenditureRead(BaseModel):
    surf_min: int = 0
    surf_kcal: float = 0.0
    workout_min: int = 0
    workout_kcal: float = 0.0
    total_kcal: float = 0.0


class TargetRead(BaseModel):
    """La cible du jour, **et de quoi elle est faite**.

    Le détail n'est pas de la décoration : une cible qui monte de 400 kcal sans
    dire pourquoi n'est pas croyable, et une cible pas croyable ne se suit pas.
    """

    kcal: int
    protein_g: int
    carb_g: int
    fat_g: int
    # Protéines rapportées au poids de corps — la façon dont on les lit.
    protein_g_per_kg: Optional[float] = None

    bmr: float
    base_kcal: float
    goal_kcal: float
    calibration_kcal: float
    expenditure: ExpenditureRead
    # Vrai quand il a fallu se rabattre sur des valeurs par défaut. L'écran le
    # dit plutôt que de faire passer une estimation pour un calcul.
    estimated: bool = False
    reasons: list[str] = []


class NutritionDay(BaseModel):
    """Tout ce dont l'écran Nutrition a besoin pour une journée, en un appel."""

    day: date
    target: TargetRead
    totals: MacroTotals
    entries: list[FoodLogRead] = []
    # Le menu prévu pour ce jour, s'il y en a un.
    planned: list["MealPlanItemRead"] = []


class BodyMetricWrite(BaseModel):
    day: Optional[date] = None
    weight_kg: Optional[float] = Field(default=None, gt=20, le=300)
    waist_cm: Optional[float] = Field(default=None, gt=40, le=200)
    note: Optional[str] = Field(default=None, max_length=200)


class BodyMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    weight_kg: Optional[float] = None
    waist_cm: Optional[float] = None
    photo_url: Optional[str] = None
    note: Optional[str] = None


class CalibrationRead(BaseModel):
    """Ce qu'a donné la recalibration déclenchée par une pesée.

    Elle ne fait rien la plupart du temps, et le dit : corriger toutes les
    semaines transformerait le bruit de la balance en oscillation de la cible.
    """

    applied: bool
    days: int = 0
    weight_change_kg: float = 0.0
    expected_change_kg: float = 0.0
    adjustment_kcal: float = 0.0
    new_calibration_kcal: float = 0.0
    reason: str = ""


class WeighInResponse(BaseModel):
    metric: BodyMetricRead
    calibration: CalibrationRead


class NutritionProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    goal: str
    activity_factor: float
    protein_g_per_kg: float
    fat_ratio: float
    calibration_kcal: float
    calibrated_on: Optional[date] = None


class NutritionProfileUpdate(BaseModel):
    goal: Optional[str] = None
    activity_factor: Optional[float] = Field(default=None, ge=1.0, le=2.2)
    protein_g_per_kg: Optional[float] = Field(default=None, ge=0.8, le=3.0)
    fat_ratio: Optional[float] = Field(default=None, ge=0.15, le=0.45)
    # Ce qui manque à Mifflin-St Jeor et qui vit sur le profil général.
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    height_m: Optional[float] = Field(default=None, gt=1.0, le=2.5)


class RecipeItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    quantity_g: float
    food_id: Optional[int] = None


class RecipeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    meals: list[str] = []
    tags: list[str] = []
    servings: int = 1
    prep_min: int = 10
    steps: Optional[str] = None
    # Par portion, calculées au semis depuis Ciqual. Nulles tant que la table
    # n'est pas importée : la recette reste lisible, sans ses macros.
    kcal: Optional[float] = None
    protein_g: Optional[float] = None
    carb_g: Optional[float] = None
    fat_g: Optional[float] = None
    items: list[RecipeItemRead] = []


class MealPlanItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day_index: int
    meal: str
    servings: float
    recipe: RecipeRead


class ShoppingLineRead(BaseModel):
    label: str
    quantity_g: float
    food_group: Optional[str] = None


class MealPlanRead(BaseModel):
    """Le menu de la semaine, et sa liste de courses agrégée.

    Sept dîners qui demandent chacun deux cents grammes de riz font un kilo
    quatre de riz, et c'est ça qu'on lit au supermarché — pas sept lignes.
    """

    week_start: date
    items: list[MealPlanItemRead] = []
    shopping: list[ShoppingLineRead] = []


class RegenerateRequest(BaseModel):
    day_index: int = Field(ge=0, le=6)
    meal: str


NutritionDay.model_rebuild()
