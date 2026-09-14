"""Nutrition — aliments, recettes, menus, journal, pesées.

Le lot 5. Trois décisions de modèle portent tout le reste :

1. **Une ligne de journal fige ses valeurs nutritionnelles.** Elle porte
   `food_id` *et* les kcal et macros calculés au moment de la saisie. C'est la
   même règle que le `conditions_snapshot` d'une session : le jour où la table
   Ciqual change de version, ou qu'Open Food Facts corrige une fiche, les
   journées déjà écrites ne doivent pas se réécrire toutes seules. Un bilan de
   la semaine dernière qui change parce qu'une base a bougé n'est plus un
   bilan.
2. **La cible calorique n'est jamais stockée.** Elle se recalcule à chaque
   lecture depuis le profil, les sessions du jour et la calibration
   (`services/nutrition`). La figer voudrait dire la recalculer à la main à
   chaque pesée, et donc l'oublier.
3. **Les valeurs sont pour 100 g, comme dans Ciqual**, et la quantité est en
   grammes. Aucune unité composite : une « portion » est un affichage, pas une
   grandeur (cf. CLAUDE.md).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import JSONVariant


class Food(Base):
    """Un aliment — table Ciqual de l'ANSES, ou produit Open Food Facts.

    Les deux sources cohabitent dans la même table parce qu'elles décrivent la
    même chose, et que le journal ne fait pas la différence au moment de la
    saisie. `source` et `source_version` sont sur chaque ligne, comme sur
    `forecasts` et pour la même raison : le jour où Ciqual publie une révision,
    il faudra pouvoir dire quelles lignes en viennent.
    """

    __tablename__ = "foods"
    __table_args__ = (
        # Clé naturelle de l'import : un code Ciqual ne doit jamais être inséré
        # deux fois, quel que soit le nombre de rejeux.
        UniqueConstraint("source", "external_id", name="uq_foods_source_external"),
        Index("ix_foods_name_normalized", "name_normalized"),
        Index("ix_foods_barcode", "barcode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # `ciqual` ou `openfoodfacts`.
    source: Mapped[str] = mapped_column(String, nullable=False, default="ciqual")
    source_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Code Ciqual (`alim_code`) ou code-barres OFF.
    external_id: Mapped[str] = mapped_column(String, nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    # Minuscules, sans accents : c'est sur cette colonne que porte la recherche.
    # La calculer à l'écriture évite un `unaccent` par requête, que SQLite n'a
    # de toute façon pas.
    name_normalized: Mapped[str] = mapped_column(String, nullable=False)
    food_group: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Pour 100 g, comme Ciqual. Nulles quand la table ne les donne pas : on ne
    # met pas de zéro, qui se lirait « cet aliment n'a pas de protéines ».
    kcal_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carb_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Recipe(Base):
    """Une recette simple — le vivier du menu de la semaine.

    Une quarantaine, semées par l'application. Elles sont **taggées** (`rapide`,
    `veggie`, `proteine`, `post-surf`) parce que c'est sur ces étiquettes que
    travaille le générateur de menu : un algorithme glouton sous contrainte de
    macros et de variété, lisible et testable, pas une IA.
    """

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    # `catalog` (semée par l'application) ou `user` (écrite ou modifiée ici).
    #
    # La distinction n'est pas décorative : le semis **remplace les ingrédients
    # en bloc** sur les recettes du catalogue, et il rejoue après chaque import
    # Ciqual. Une modification faite sur une ligne `catalog` serait donc effacée
    # sans prévenir. D'où la règle : modifier une recette du catalogue en crée
    # une **copie** `user`, que le semis ne touche jamais.
    source: Mapped[str] = mapped_column(
        String, nullable=False, default="catalog", server_default="catalog"
    )
    # Nul pour le catalogue, qui est commun. Renseigné pour une recette écrite
    # par l'utilisateur — le projet est mono-utilisateur, mais une recette
    # perso qui ne dit pas à qui elle est finirait par être servie à tout le
    # monde le jour où il y en aurait deux.
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # La recette du catalogue dont celle-ci est la version perso. Gardée pour
    # pouvoir dire « ta version de Poulet riz brocoli », et pour ne pas
    # reproposer les deux côte à côte comme si elles étaient étrangères.
    based_on_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    # `breakfast`, `lunch`, `dinner`, `snack` — les repas où elle a sa place.
    meals: Mapped[list[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONVariant, nullable=False, default=list)
    servings: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prep_min: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Par **portion**, figées au semis depuis les ingrédients. Recalculées à
    # chaque semis, jamais à la lecture : un menu de la semaine qui changerait
    # de macros parce qu'un aliment a bougé ne serait plus un menu.
    kcal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carb_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["RecipeItem"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="RecipeItem.position"
    )


class RecipeItem(Base):
    """Un ingrédient. `food_id` est **facultatif** : une recette semée nomme ses
    ingrédients avant que la table Ciqual ne soit importée, et elle doit rester
    lisible dans cet état — sans valeurs nutritionnelles, mais lisible."""

    __tablename__ = "recipe_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String, nullable=False)
    # Nom Ciqual recherché au semis. Gardé pour pouvoir réessayer l'appariement
    # après un import, sans réécrire les recettes.
    ciqual_query: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    food_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
    quantity_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class FoodLog(Base):
    """Une ligne du journal — un aliment, une quantité, un repas.

    Les valeurs nutritionnelles sont **figées à la saisie**. Elles pourraient se
    recalculer depuis `food_id`, et c'est justement ce qu'on ne veut pas : le
    jour où Ciqual change de version ou qu'une fiche Open Food Facts est
    corrigée, un bilan de la semaine dernière ne doit pas changer tout seul.
    """

    __tablename__ = "food_log"
    __table_args__ = (Index("ix_food_log_user_day", "user_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Journée **locale** : un repas de 23 h 30 appartient à ce jour-là, pas au
    # lendemain UTC.
    day: Mapped[date] = mapped_column(Date, nullable=False)
    meal: Mapped[str] = mapped_column(String, nullable=False, default="lunch")

    food_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("foods.id", ondelete="SET NULL"), nullable=True
    )
    recipe_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    # Le nom au moment de la saisie : une ligne reste lisible même si l'aliment
    # disparaît de la base.
    label: Mapped[str] = mapped_column(String, nullable=False)
    quantity_g: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    kcal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carb_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MealPlan(Base):
    """Le menu d'une semaine. Une ligne par semaine et par utilisateur."""

    __tablename__ = "meal_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_meal_plans_user_week"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Le lundi de la semaine, en date locale.
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["MealPlanItem"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MealPlanItem.day_index, MealPlanItem.meal",
    )


class MealPlanItem(Base):
    __tablename__ = "meal_plan_items"
    __table_args__ = (
        UniqueConstraint(
            "plan_id", "day_index", "meal", name="uq_meal_plan_items_slot"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 0 = lundi.
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    meal: Mapped[str] = mapped_column(String, nullable=False)

    # **Facultative**, et c'est toute la nouveauté : un créneau peut exister
    # sans plat. « Jeudi soir je ne suis pas là » est une information qu'on
    # pose *avant* de générer la semaine, et le générateur doit pouvoir la
    # lire. Un créneau `away` sans recette n'est pas un trou, c'est une
    # réponse.
    recipe_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=True
    )
    # `planned` ou `away`. `away` = pas chez soi, donc rien à prévoir et rien à
    # acheter — c'est la seule chose qui sort un plat de la liste de courses.
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="planned", server_default="planned"
    )
    servings: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    recipe: Mapped[Optional["Recipe"]] = relationship(lazy="selectin")


class RecipeNote(Base):
    """Ce que **l'utilisateur** pense d'une recette : favorite, et sa note libre.

    Séparée de `recipes` pour une raison simple : le catalogue est commun et
    semé, la note est personnelle et ne doit jamais être écrasée par un semis.
    Poser `favorite` sur `recipes` reviendrait à mettre une préférence dans une
    table que l'application réécrit toute seule.

    La note libre est le seul champ de texte de l'écran Nutrition — « sans le
    piment c'est meilleur », « cuire le riz 2 min de plus ». C'est ce qui
    transforme une banque de recettes générique en carnet de cuisine.
    """

    __tablename__ = "recipe_notes"
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_recipe_notes_user_recipe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipe_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    favorite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Combien de fois elle a été cuisinée — incrémenté quand on la journalise.
    # Calculable depuis `food_log`, mais une requête d'agrégat par recette à
    # chaque ouverture de la bibliothèque coûterait plus cher que la colonne.
    cooked_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BodyMetric(Base):
    """La pesée hebdomadaire — poids, tour de taille, photo optionnelle.

    Elle sert deux choses : la tendance affichée sur Nutrition, et la
    **recalibration** de la cible calorique. Sans elle, la cible reste une
    estimation de formule, et l'estimation calorique d'une session de surf est
    très approximative (cf. PROJET.md §10.6).

    Le tour de taille est là parce que « objectif six pack » a été traduit en
    « composition corporelle » : un objectif mesurable tient, un objectif
    visuel non.
    """

    __tablename__ = "body_metrics"
    __table_args__ = (
        # Une pesée par jour : se repeser le même jour remplace, comme une
        # mesure d'objectif.
        UniqueConstraint("user_id", "day", name="uq_body_metrics_user_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    waist_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NutritionProfile(Base):
    """Les réglages qui font la cible : objectif, activité, et la calibration.

    `calibration_kcal` est le seul terme **appris** : il se corrige toutes les
    deux à trois semaines sur l'écart entre la variation de poids réelle et
    celle qu'on avait prédite. C'est lui qui rattrape tout ce que la formule ne
    sait pas — le métabolisme propre, la dépense d'une session de surf, et le
    fait qu'on ne pèse pas tout ce qu'on mange.
    """

    __tablename__ = "nutrition_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # `maintain`, `cut`, `bulk`.
    goal: Mapped[str] = mapped_column(String, nullable=False, default="maintain")
    # Facteur d'activité **de base**, hors sport : la dépense des sessions est
    # ajoutée à part, par MET. 1,3 = travail assis et un peu de marche.
    activity_factor: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.3, server_default="1.3"
    )
    # Protéines visées, en grammes par kilo de poids de corps.
    protein_g_per_kg: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.8, server_default="1.8"
    )
    # Part des lipides dans les calories, en fraction.
    fat_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.28, server_default="0.28"
    )
    # Le terme appris. Positif = on mange plus que la formule ne le dit.
    calibration_kcal: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    calibrated_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
