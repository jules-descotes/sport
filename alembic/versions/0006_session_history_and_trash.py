"""lot 3 (13/09) — historique des snapshots et corbeille des sessions

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-13

Les sessions se créent et se modifient désormais **depuis le navigateur**, pas
seulement par le raccourci iPhone. Deux colonnes rendent la modification sûre :

- `snapshot_history` — la pile des `conditions_snapshot` remplacés. Changer le
  spot ou l'heure d'une session refait le figeage des conditions ; l'ancien ne
  doit **jamais** disparaître en silence. C'est la seule donnée du projet qui
  soit irrattrapable après coup (cf. CLAUDE.md, règle 7), et une correction
  faite de bonne foi ne doit pas pouvoir en détruire une version.
- `deleted_at` — corbeille de trente jours. Un doigt mouillé supprime aussi
  bien qu'il déclenche le raccourci ; une suppression immédiate et définitive
  d'une ligne d'apprentissage est un risque qu'on n'a aucune raison de prendre.

Une migration = une transaction (cf. CLAUDE.md) : ce fichier ne fait que ce
qu'annonce son titre.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("surf_sessions") as batch:
        # JSON et pas JSONB ici : `batch_alter_table` recrée la table sous
        # SQLite, et le type variant du modèle (`JSONVariant`) rend déjà du
        # JSONB sous Postgres à la lecture comme à l'écriture.
        batch.add_column(sa.Column("snapshot_history", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
        )

    # L'historique remonte « les sessions à noter » et la corbeille filtre
    # dessus : l'index existant (user_id, status) ne suffit plus.
    op.create_index(
        "ix_surf_sessions_user_deleted", "surf_sessions", ["user_id", "deleted_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_surf_sessions_user_deleted", table_name="surf_sessions")

    with op.batch_alter_table("surf_sessions") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("snapshot_history")
