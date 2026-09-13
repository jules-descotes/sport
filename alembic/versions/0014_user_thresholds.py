"""13/09 (retours n° 4) — seuils personnels de qualité

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-13

Huit nombres qui disent où commence le bon.

Jusqu'ici, le tableau horaire teintait par **intensité** — plus la houle est
grosse, plus c'est saturé. C'est exact et sans intérêt : une houle de 3 m est
grosse, ce qui n'est pas la même chose que bonne, et l'écran ne répondait donc
jamais à la question qu'on lui pose en l'ouvrant. Le score de démarrage, lui,
lisait des bandes écrites en dur dans `services/scoring.py` — c'est-à-dire
l'avis de personne.

Une ligne par utilisateur, contrainte d'unicité pour que ce soit vrai en base
et pas seulement dans le code.

**Aucune valeur n'est semée ici.** Les défauts vivent dans
`schemas/thresholds.py`, où ils se corrigent sans migration, et la ligne est
créée à la première lecture. Semer du contenu dans une migration oblige à
écrire une migration par changement d'avis — la même règle qu'au lot 4 pour le
catalogue d'exercices.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_thresholds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_good_s", sa.Float(), nullable=False),
        sa.Column("period_great_s", sa.Float(), nullable=False),
        sa.Column("wind_top_kt", sa.Float(), nullable=False),
        sa.Column("wind_strong_kt", sa.Float(), nullable=False),
        sa.Column("wind_very_strong_kt", sa.Float(), nullable=False),
        sa.Column("wave_min_m", sa.Float(), nullable=False),
        sa.Column("wave_good_m", sa.Float(), nullable=False),
        sa.Column("wave_big_m", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_thresholds_user_id", "user_thresholds", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_user_thresholds_user_id", table_name="user_thresholds")
    op.drop_table("user_thresholds")
