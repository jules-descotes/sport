"""lot 6 (13/09) — suivi d'habitudes quotidiennes

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-13

Des compteurs libres, définis par Jules, saisis en un tap depuis Jour.

Deux décisions de schéma, et elles sont irrattrapables après coup :

1. **Les événements sont horodatés à la seconde**, pas agrégés par jour.
   L'intérêt de ces lignes au lot 6 est de les croiser avec le **ressenti des
   sessions du lendemain** — « les jours où j'ai bu trois verres, je note ma
   forme un point en dessous » — et un tel croisement se fait sur des instants.
   Une colonne par jour posée aujourd'hui détruirait cette possibilité pour
   toujours, exactement comme un `conditions_snapshot` réduit à un point.
2. **Rien de jugeant n'est stocké.** Pas de série, pas de taux de réussite, pas
   d'objectif obligatoire. Un compteur et des événements. Ce qui se calcule à
   l'affichage est une tendance, jamais une note.

Une habitude se met en **pause** (`is_active`) plutôt que de se supprimer : les
événements passés sont de la donnée, et une envie du dimanche soir ne doit pas
pouvoir effacer trois mois de comptage.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "habits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("icon", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column(
            "target_period", sa.String(length=10), nullable=False, server_default="day"
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
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
    )
    op.create_index("ix_habits_user_active", "habits", ["user_id", "is_active"])

    op.create_table(
        "habit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "habit_id",
            sa.Integer(),
            sa.ForeignKey("habits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("note", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_habit_events_habit_at", "habit_events", ["habit_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_habit_events_habit_at", table_name="habit_events")
    op.drop_table("habit_events")
    op.drop_index("ix_habits_user_active", table_name="habits")
    op.drop_table("habits")
