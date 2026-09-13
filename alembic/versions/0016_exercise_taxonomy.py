"""13/09 (retours n° 3 et n° 4) — taxonomie des exercices, français et images

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-13

Ce que le générateur de séances a besoin de savoir d'un exercice, et ce que
l'écran a besoin pour le dire en français.

**Taxonomie** — `group_key`, `pattern`, `equipment`, `difficulty`,
`effort_kind`, `unilateral`. Le pattern de mouvement compte plus que le groupe
pour composer une séance : trois tirages d'affilée font une séance de tirage
quel que soit le muscle visé, et c'est exactement ce qu'il faut éviter de
produire par accident.

**Ce qui n'est pas reconnu vaut « a-classer »**, jamais une valeur plausible.
Une valeur et pas un NULL : « à classer » est un état qu'on peut compter et
corriger, un NULL se confondrait avec « pas encore importé ». C'est la leçon de
`sport=surfing` appliquée une deuxième fois — une étiquette vraisemblable posée
en masse sur des données qu'on n'a pas relues produit un catalogue qui a l'air
juste et qui ne l'est pas.

**Français** — `name_fr` et `description_fr`, nullables et le restant. Un
exercice sans nom français n'entre ni dans le générateur ni dans une formule :
« Barbell Hip Thrust » au milieu d'une séance ne se lit pas à bout de bras.
Semer une traduction approximative vaudrait moins que ne rien dire.

**Images** — `images` porte la liste complète (free-exercise-db en donne deux
par exercice, et c'est leur alternance qui montre le mouvement). `image_url`
reste la première : les écrans qui n'en veulent qu'une continuent de marcher.

Les valeurs sont posées par l'import et par le semis, pas ici : elles évoluent,
et on n'écrit pas une migration par correction de dictionnaire.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNCLASSIFIED = "a-classer"


def upgrade() -> None:
    op.add_column(
        "exercises",
        sa.Column(
            "group_key",
            sa.String(length=20),
            nullable=False,
            server_default=UNCLASSIFIED,
        ),
    )
    op.add_column(
        "exercises",
        sa.Column(
            "pattern",
            sa.String(length=24),
            nullable=False,
            server_default=UNCLASSIFIED,
        ),
    )
    op.add_column(
        "exercises",
        sa.Column(
            "equipment",
            sa.String(length=20),
            nullable=False,
            server_default=UNCLASSIFIED,
        ),
    )
    # 3 par défaut — le milieu. Une difficulté fausse fait proposer une séance
    # infaisable ; une difficulté absente empêcherait le générateur de
    # fonctionner du tout, et c'est pire.
    op.add_column(
        "exercises",
        sa.Column("difficulty", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "exercises",
        sa.Column(
            "effort_kind",
            sa.String(length=8),
            nullable=False,
            server_default="reps",
        ),
    )
    # « Par côté » double la durée d'une séance : le générateur doit le savoir.
    op.add_column(
        "exercises",
        sa.Column(
            "unilateral", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    op.add_column(
        "exercises", sa.Column("name_fr", sa.String(length=120), nullable=True)
    )
    op.add_column("exercises", sa.Column("description_fr", sa.Text(), nullable=True))
    op.add_column("exercises", sa.Column("images", sa.JSON(), nullable=True))

    # Le générateur filtre sur le groupe et le pattern à chaque demande, sur
    # 1 700 lignes. Deux index, et pas un de plus.
    op.create_index("ix_exercises_group_key", "exercises", ["group_key"])
    op.create_index("ix_exercises_pattern", "exercises", ["pattern"])

    # Les corrections manuelles du niveau, par groupe. Une colonne JSON sur le
    # profil plutôt qu'une table : ce sont au plus huit entiers, ils se lisent
    # toujours ensemble, et une table pour ça coûterait une jointure à chaque
    # génération pour rien.
    op.add_column(
        "profiles", sa.Column("training_levels", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("profiles", "training_levels")
    op.drop_index("ix_exercises_pattern", table_name="exercises")
    op.drop_index("ix_exercises_group_key", table_name="exercises")
    for column in (
        "images",
        "description_fr",
        "name_fr",
        "unilateral",
        "effort_kind",
        "difficulty",
        "equipment",
        "pattern",
        "group_key",
    ):
        op.drop_column("exercises", column)
