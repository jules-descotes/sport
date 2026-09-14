"""13/09 (retours n° 5) — le menu se réduit à deux repas, et les recettes deviennent les siennes

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-13

Quatre changements, et ils tiennent tous à la même observation : **le menu
n'était pas suivi**.

1. **`meal_plan_items.recipe_id` devient facultative.** Un créneau peut exister
   sans plat, parce qu'il faut pouvoir dire « jeudi soir je ne suis pas là »
   *avant* de générer la semaine. Sans colonne nullable, cette phrase n'aurait
   nulle part où s'écrire, et le générateur continuerait de prévoir un dîner
   qu'on n'aurait jamais mangé.
2. **`meal_plan_items.status`** — `planned` ou `away`. C'est la seule chose qui
   sort un plat de la liste de courses, et c'est exactement ce qu'on lui
   demande : ne pas acheter le poisson d'un dîner au restaurant.
3. **Les repas planifiés passent de quatre à deux.** Le petit déjeuner ne se
   choisit pas le dimanche pour le mardi — il se répète. Un en-cas planifié est
   un en-cas qu'on ne mange pas. Les lignes `breakfast` et `snack` déjà en base
   sont **supprimées** : un menu est une intention, pas un historique, et
   laisser vingt-huit créneaux dont quatorze morts ferait une liste de courses
   fausse dès le premier jour. Le journal, lui, ne bouge pas — `food_log` garde
   ses quatre repas, parce qu'on mange toujours le matin.
4. **`recipes.source` / `user_id` / `based_on_id`, et `recipe_notes`.** Le semis
   remplace les ingrédients **en bloc** sur les recettes du catalogue, et il
   rejoue après chaque import Ciqual : une modification faite sur une ligne
   semée serait effacée sans prévenir. Modifier une recette du catalogue en
   crée donc une copie `user`, que le semis ne touche jamais. Les favoris et
   les notes libres vivent dans leur propre table pour la même raison — une
   préférence n'a rien à faire dans une table que l'application réécrit toute
   seule.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# **0018 et non 0015** : le numéro dit la place dans la chaîne, jamais la date
# à laquelle on a commencé à écrire le fichier. Celle-ci a été rédigée pendant
# que 0016 et 0017 étaient livrées, et elle se chaîne donc derrière elles —
# porter le numéro 0015 en queue de chaîne rendait l'ordre réel illisible, et
# c'est précisément ce qu'un numéro de révision sert à dire.
revision: str = "0018"
down_revision: Union[str, Sequence[str], None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Les recettes : catalogue commun, versions perso ────────────────────
    with op.batch_alter_table("recipes") as batch:
        batch.add_column(
            sa.Column(
                "source",
                sa.String(),
                nullable=False,
                server_default="catalog",
            )
        )
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("based_on_id", sa.Integer(), nullable=True))
        # SQLite ne sait pas ajouter une clé étrangère par ALTER : c'est
        # `batch_alter_table` qui recrée la table, et il lui faut les
        # contraintes nommées pour pouvoir les reposer.
        batch.create_foreign_key(
            "fk_recipes_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_foreign_key(
            "fk_recipes_based_on_id",
            "recipes",
            ["based_on_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_recipes_user_id", "recipes", ["user_id"])

    op.create_table(
        "recipe_notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # `sa.false()`, jamais `sa.text("0")` : Postgres refuse un entier comme
        # défaut de booléen (`DEFAULT 0` -> erreur de type), là où SQLite
        # l'accepte sans broncher. C'est exactement ce qui a mis la production
        # à terre le 14/09. `sa.false()` rend `false` sur Postgres et `0` sur
        # SQLite — le dialecte tranche, pas nous.
        sa.Column(
            "favorite", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "cooked_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
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
        sa.UniqueConstraint(
            "user_id", "recipe_id", name="uq_recipe_notes_user_recipe"
        ),
    )
    op.create_index("ix_recipe_notes_user_id", "recipe_notes", ["user_id"])
    op.create_index("ix_recipe_notes_recipe_id", "recipe_notes", ["recipe_id"])

    # ── Le menu : deux repas, et le créneau « pas là » ─────────────────────
    #
    # La purge passe **avant** le changement de schéma : elle ne dépend pas de
    # lui, et la faire après voudrait dire créer des colonnes pour des lignes
    # qu'on s'apprête à jeter.
    op.execute(
        sa.text(
            "DELETE FROM meal_plan_items WHERE meal NOT IN ('lunch', 'dinner')"
        )
    )

    with op.batch_alter_table("meal_plan_items") as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(),
                nullable=False,
                server_default="planned",
            )
        )
        batch.alter_column("recipe_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Les créneaux sans plat n'ont pas d'équivalent dans l'ancien schéma : un
    # `recipe_id` non nul est impossible à inventer, donc on les retire. C'est
    # la seule lecture honnête d'un retour arrière — un menu se régénère.
    op.execute(sa.text("DELETE FROM meal_plan_items WHERE recipe_id IS NULL"))

    with op.batch_alter_table("meal_plan_items") as batch:
        batch.alter_column("recipe_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("status")

    op.drop_index("ix_recipe_notes_recipe_id", table_name="recipe_notes")
    op.drop_index("ix_recipe_notes_user_id", table_name="recipe_notes")
    op.drop_table("recipe_notes")

    # Les recettes perso partent avec la colonne qui les distingue : les
    # laisser derrière ferait passer une version modifiée pour une recette du
    # catalogue, et le semis suivant l'écraserait sans rien dire.
    op.execute(sa.text("DELETE FROM recipes WHERE source = 'user'"))

    op.drop_index("ix_recipes_user_id", table_name="recipes")
    with op.batch_alter_table("recipes") as batch:
        batch.drop_constraint("fk_recipes_based_on_id", type_="foreignkey")
        batch.drop_constraint("fk_recipes_user_id", type_="foreignkey")
        batch.drop_column("based_on_id")
        batch.drop_column("user_id")
        batch.drop_column("source")
