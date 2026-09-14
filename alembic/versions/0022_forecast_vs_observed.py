"""15/09 — les paires prévision ↔ mesure, pour mesurer le biais (§7.3)

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-15

Une ligne = **une heure mesurée, vue par un run de prévision**. Une même heure
en produit plusieurs : celle annoncée trois jours avant, celle annoncée la
veille, celle annoncée le matin. C'est exactement la question qu'on veut
poser — « de combien le modèle se trompe *à tel délai* » — et c'est
l'historisation des runs du lot 1 ter qui la rend posable.

`lead_hours` est **stocké** et non recalculé : c'est la colonne sur laquelle on
agrège, et une différence de dates dans un `GROUP BY` ne s'indexe pas.

`model` et `model_version` sont sur chaque ligne, comme sur `forecasts`. Le
jour où Météo-France recalibre MFWAM, le biais mesuré avant et après ne décrit
pas le même modèle, et les moyenner effacerait précisément ce qu'on cherchait à
voir.

> Cette table ne mélange rien : `forecasts` reste la prévision, `observations`
> reste la mesure. Aucune de ses colonnes n'entre dans un vecteur de features —
> c'est un tableau de bord, pas une source d'entraînement (cf. PROJET.md §7.1).

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "forecast_vs_observed",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.String(), nullable=False),
        sa.Column("spot_id", sa.Integer(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_hours", sa.Float(), nullable=False),
        sa.Column("forecast_hm0_m", sa.Float(), nullable=True),
        sa.Column("observed_hm0_m", sa.Float(), nullable=True),
        sa.Column("forecast_period_s", sa.Float(), nullable=True),
        sa.Column("observed_period_s", sa.Float(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("model_version", sa.String(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["spot_id"], ["spots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id",
            "ts",
            "run_ts",
            name="uq_forecast_vs_observed_station_ts_run",
        ),
    )
    op.create_index("ix_forecast_vs_observed_ts", "forecast_vs_observed", ["ts"])
    op.create_index(
        "ix_forecast_vs_observed_station_lead",
        "forecast_vs_observed",
        ["station_id", "lead_hours"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_forecast_vs_observed_station_lead", table_name="forecast_vs_observed"
    )
    op.drop_index("ix_forecast_vs_observed_ts", table_name="forecast_vs_observed")
    op.drop_table("forecast_vs_observed")
