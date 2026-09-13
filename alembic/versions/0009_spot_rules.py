"""lot 5 (13/09) — les critères de Jules par spot favori

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-13

« Parlementia marche en houle d'ouest de 1,2 à 2,5 m, période au moins 11 s,
vent d'est, marée montante. » Cette phrase-là, aucun modèle ne l'apprendra
avant plusieurs saisons — et Jules l'a déjà. `spot_rules` est l'endroit où il
la pose.

C'est l'*a priori* du §7.4 du PROJET.md, mais c'est **le sien** : il prime donc
sur l'orientation calculée depuis le trait de côte OSM, qui ne sait rien du
récif ni de la fosse. Il ne remplace pas l'apprentissage, il l'amorce — le jour
où un spot atteint ses vingt-cinq sessions notées, le modèle passe devant.

Tous les champs sont **nullables ou vides**, et c'est le cœur du modèle : un
champ vide n'est pas une valeur par défaut, c'est une absence de contrainte. On
ne remplit pas les trous avec des seuils inventés.

`user_id` est dans la clé unique dès maintenant, alors qu'il n'y a qu'un
utilisateur : le jour où l'app s'ouvre aux potes (PROJET.md §11), les critères
de Jules ne doivent pas devenir ceux de tout le monde, et ajouter la colonne
après coup voudrait dire rejouer une migration sur de la donnée saisie à la
main.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "spot_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "spot_id",
            sa.Integer(),
            sa.ForeignKey("spots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("wave_height_min_m", sa.Float(), nullable=True),
        sa.Column("wave_height_max_m", sa.Float(), nullable=True),
        sa.Column("wave_period_min_s", sa.Float(), nullable=True),
        sa.Column("swell_sectors", sa.JSON(), nullable=False),
        sa.Column("wind_sectors", sa.JSON(), nullable=False),
        sa.Column("wind_max_kt", sa.Float(), nullable=True),
        sa.Column("tide_phases", sa.JSON(), nullable=False),
        sa.Column("hour_min", sa.Integer(), nullable=True),
        sa.Column("hour_max", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("user_id", "spot_id", name="uq_spot_rules_user_spot"),
    )
    op.create_index("ix_spot_rules_user_id", "spot_rules", ["user_id"])
    op.create_index("ix_spot_rules_spot_id", "spot_rules", ["spot_id"])


def downgrade() -> None:
    op.drop_index("ix_spot_rules_spot_id", table_name="spot_rules")
    op.drop_index("ix_spot_rules_user_id", table_name="spot_rules")
    op.drop_table("spot_rules")
