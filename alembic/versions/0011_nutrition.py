"""lot 5 — nutrition : aliments, recettes, menus, journal, pesées

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-13

Le lot 5 au complet. Huit tables, et trois décisions qui les structurent :

1. **Une ligne de journal fige ses valeurs nutritionnelles.** Même règle que le
   `conditions_snapshot` d'une session : le jour où Ciqual change de version ou
   qu'une fiche Open Food Facts est corrigée, un bilan de la semaine dernière ne
   doit pas se réécrire tout seul.
2. **La cible calorique n'est pas une table.** Elle se recalcule à chaque
   lecture depuis le profil, les sessions du jour et la calibration
   (`services/nutrition`). La figer voudrait dire la recalculer à la main à
   chaque pesée, donc l'oublier. Seuls les **réglages** sont stockés, dans
   `nutrition_profiles`, dont le terme `calibration_kcal` est le seul appris.
3. **`birth_date` et `sex` arrivent sur `profiles`**, parce que Mifflin-St Jeor
   en a besoin et qu'ils n'y étaient pas. Nullables : sans eux, la cible se
   rabat sur une estimation dégradée et le dit, plutôt que d'inventer un âge.

Le **contenu** — la table Ciqual et les recettes — n'est pas semé ici. Ciqual
s'importe par `scripts/import_ciqual.py` depuis le CSV de data.gouv.fr ; les
recettes sont semées par l'application au premier accès à l'écran, comme le
catalogue d'exercices du lot 4 : elles évolueront, et on n'écrit pas une
migration par correction de quantité.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mifflin-St Jeor a besoin de l'âge et du sexe. Nullables : une cible
    # dégradée qui se signale vaut mieux qu'un âge inventé.
    with op.batch_alter_table("profiles") as batch:
        batch.add_column(sa.Column("birth_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("sex", sa.String(), nullable=True))

    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_version", sa.String(), nullable=True),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_normalized", sa.String(), nullable=False),
        sa.Column("food_group", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("barcode", sa.String(), nullable=True),
        sa.Column("kcal_100g", sa.Float(), nullable=True),
        sa.Column("protein_100g", sa.Float(), nullable=True),
        sa.Column("carb_100g", sa.Float(), nullable=True),
        sa.Column("fat_100g", sa.Float(), nullable=True),
        sa.Column("fiber_100g", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("source", "external_id", name="uq_foods_source_external"),
    )
    op.create_index("ix_foods_name_normalized", "foods", ["name_normalized"])
    op.create_index("ix_foods_barcode", "foods", ["barcode"])

    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("meals", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("prep_min", sa.Integer(), nullable=False),
        sa.Column("steps", sa.Text(), nullable=True),
        sa.Column("kcal", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carb_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_recipes_slug", "recipes", ["slug"], unique=True)

    op.create_table(
        "recipe_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("ciqual_query", sa.String(), nullable=True),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("quantity_g", sa.Float(), nullable=False),
    )
    op.create_index("ix_recipe_items_recipe_id", "recipe_items", ["recipe_id"])

    op.create_table(
        "food_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("meal", sa.String(), nullable=False),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("quantity_g", sa.Float(), nullable=False),
        sa.Column("kcal", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carb_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("fiber_g", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_food_log_user_day", "food_log", ["user_id", "day"])

    op.create_table(
        "meal_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "week_start", name="uq_meal_plans_user_week"),
    )

    op.create_table(
        "meal_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("meal_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("meal", sa.String(), nullable=False),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("servings", sa.Float(), nullable=False),
        sa.UniqueConstraint(
            "plan_id", "day_index", "meal", name="uq_meal_plan_items_slot"
        ),
    )
    op.create_index("ix_meal_plan_items_plan_id", "meal_plan_items", ["plan_id"])

    op.create_table(
        "body_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("waist_cm", sa.Float(), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "day", name="uq_body_metrics_user_day"),
    )
    op.create_index("ix_body_metrics_user_id", "body_metrics", ["user_id"])

    op.create_table(
        "nutrition_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("goal", sa.String(), nullable=False, server_default="maintain"),
        sa.Column(
            "activity_factor", sa.Float(), nullable=False, server_default="1.3"
        ),
        sa.Column(
            "protein_g_per_kg", sa.Float(), nullable=False, server_default="1.8"
        ),
        sa.Column("fat_ratio", sa.Float(), nullable=False, server_default="0.28"),
        sa.Column("calibration_kcal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("calibrated_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_nutrition_profiles_user_id", "nutrition_profiles", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_nutrition_profiles_user_id", table_name="nutrition_profiles")
    op.drop_table("nutrition_profiles")
    op.drop_index("ix_body_metrics_user_id", table_name="body_metrics")
    op.drop_table("body_metrics")
    op.drop_index("ix_meal_plan_items_plan_id", table_name="meal_plan_items")
    op.drop_table("meal_plan_items")
    op.drop_table("meal_plans")
    op.drop_index("ix_food_log_user_day", table_name="food_log")
    op.drop_table("food_log")
    op.drop_index("ix_recipe_items_recipe_id", table_name="recipe_items")
    op.drop_table("recipe_items")
    op.drop_index("ix_recipes_slug", table_name="recipes")
    op.drop_table("recipes")
    op.drop_index("ix_foods_barcode", table_name="foods")
    op.drop_index("ix_foods_name_normalized", table_name="foods")
    op.drop_table("foods")

    with op.batch_alter_table("profiles") as batch:
        batch.drop_column("sex")
        batch.drop_column("birth_date")
