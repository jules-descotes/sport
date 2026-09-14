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
    """Un ingrédient, avec **l'unité dans laquelle on l'achète**.

    `quantity_g` reste la grandeur — c'est elle qui calcule les macros. Le
    reste est sa lecture : deux œufs, un avocat, 200 g de riz. Personne n'a
    jamais cassé « 110 g d'œufs ».
    """

    label: str
    quantity_g: float
    food_id: Optional[int] = None
    unit: str = "g"
    quantity: float = 0.0
    unit_label: Optional[str] = None


class RecipeRead(BaseModel):
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

    # `catalog` ou `user`. Une version perso ne se modifie pas comme une
    # recette semée : l'une est à soi, l'autre se dédouble quand on y touche.
    source: str = "catalog"
    based_on_id: Optional[int] = None
    # Ce que l'utilisateur en pense. Vides tant qu'il n'a rien dit.
    favorite: bool = False
    note: Optional[str] = None
    cooked_count: int = 0


class RecipeItemWrite(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    quantity_g: float = Field(gt=0, le=5000)
    # Le nom cherché dans Ciqual. Facultatif : à défaut, on cherche le libellé
    # lui-même, ce qui marche pour « Riz blanc cuit » et pas pour « le riz de
    # mardi ». L'ingrédient reste lisible dans les deux cas.
    ciqual_query: Optional[str] = Field(default=None, max_length=120)


class RecipeWrite(BaseModel):
    """Une recette écrite ou modifiée à la main.

    Tous les champs sont facultatifs à la modification : on corrige une
    quantité sans réécrire la recette. À la création, `name` et `items` sont
    exigés par la route — une recette sans ingrédients n'a pas de macros, et
    une recette sans macros ne peut pas entrer dans un menu.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    meals: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    servings: Optional[int] = Field(default=None, ge=1, le=12)
    prep_min: Optional[int] = Field(default=None, ge=0, le=240)
    steps: Optional[str] = Field(default=None, max_length=4000)
    items: Optional[list[RecipeItemWrite]] = None


class RecipeNoteWrite(BaseModel):
    """Le favori et la note libre. Les deux sont indépendants : on peut noter
    une recette sans l'aimer, et l'aimer sans avoir rien à en dire."""

    favorite: Optional[bool] = None
    note: Optional[str] = Field(default=None, max_length=2000)


class MealPlanItemRead(BaseModel):
    day_index: int
    meal: str
    servings: float
    # **Nulle** quand le créneau est `away` sans plat, ou quand il reste à
    # remplir. Un créneau vide est un état du menu, pas une anomalie.
    recipe: Optional[RecipeRead] = None
    # `planned` ou `away`.
    status: str = "planned"


class ShoppingLineRead(BaseModel):
    """Une ligne de courses — et **l'unité dans laquelle on l'achète**.

    `quantity_g` est le total agrégé, toujours. `unit` / `quantity` /
    `unit_label` sont sa traduction au supermarché : trois œufs, un litre et
    demi de lait, quatre cents grammes de riz.
    """

    label: str
    quantity_g: float
    food_group: Optional[str] = None
    unit: str = "g"
    quantity: float = 0.0
    unit_label: Optional[str] = None


class MealPlanRead(BaseModel):
    """Le menu de la semaine, et sa liste de courses agrégée.

    Sept dîners qui demandent chacun deux cents grammes de riz font un kilo
    quatre de riz, et c'est ça qu'on lit au supermarché — pas sept lignes.

    Les créneaux `away` n'entrent pas dans la liste : un dîner qu'on ne prendra
    pas chez soi n'a rien à faire dans le caddie.
    """

    week_start: date
    items: list[MealPlanItemRead] = []
    shopping: list[ShoppingLineRead] = []


class SlotRef(BaseModel):
    """Un créneau du menu : un jour, un repas."""

    day_index: int = Field(ge=0, le=6)
    meal: str


class RegenerateRequest(SlotRef):
    pass


class SetRecipeRequest(SlotRef):
    """Poser **cette** recette sur ce créneau. Le tirage propose, on dispose."""

    recipe_id: int
    servings: float = Field(default=1.0, gt=0, le=10)


class SwapRequest(BaseModel):
    """Échanger deux créneaux. Le mercredi soir passe au vendredi, et
    réciproquement — y compris quand l'un des deux est vide."""

    a: SlotRef
    b: SlotRef


class AwayRequest(SlotRef):
    """« Je ne suis pas chez moi. »

    `away=False` fait revenir le créneau : si le plat d'origine est encore là,
    il reprend sa place ; sinon on en tire un. Rentrer plus tôt que prévu ne
    doit pas laisser un trou.
    """

    away: bool = True


NutritionDay.model_rebuild()
