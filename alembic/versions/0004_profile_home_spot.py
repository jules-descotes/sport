"""lot 1 ter — spot favori dans le profil

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-12

« Une seule prévision par défaut, celle du spot favori du profil » (décidé le
12/09 au soir, cf. PROJET.md §11). Cette colonne est ce qui rend la décision
applicable : elle porte l'écran Jour, et elle décide du niveau d'ingestion
`home` — le seul que le job planifié interroge.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite ne sait pas ajouter une clé étrangère par ALTER : `batch_alter_table`
    # recrée la table, et émet un ALTER ordinaire sous Postgres.
    with op.batch_alter_table("profiles") as batch:
        batch.add_column(sa.Column("home_spot_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_profiles_home_spot_id",
            "spots",
            ["home_spot_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.drop_constraint("fk_profiles_home_spot_id", type_="foreignkey")
        batch.drop_column("home_spot_id")
