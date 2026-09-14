"""15/09 — le compteur d'appels journalier, en base et pas en mémoire

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-15

CANDHIS accorde 150 requêtes par jour et renvoie un 429 au-delà — et, plus
sérieux, un 423 quand une IP est bannie. On s'arrête donc à 140, comptés.

Le compteur est **en base** parce que le conteneur Railway redémarre. En
mémoire, il repartirait de zéro à chaque redéploiement, et « 140 par jour » ne
voudrait plus rien dire le jour où on pousse cinq fois de suite. C'est la même
leçon que `run_ts` au lot 1 ter : ce qui doit survivre au redémarrage vit dans
Postgres.

Le jour est en **UTC**. Le quota du Cerema se remet à zéro selon leur journée à
eux, qu'on ne connaît pas ; c'est la marge de dix qui absorbe le décalage, pas
un fuseau deviné.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_quota",
        sa.Column("id", sa.Integer(), nullable=False),
        # `candhis` aujourd'hui. La colonne existe pour que le prochain
        # fournisseur à quota n'ait pas besoin d'une deuxième table.
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "day", name="uq_api_quota_provider_day"),
    )


def downgrade() -> None:
    op.drop_table("api_quota")
