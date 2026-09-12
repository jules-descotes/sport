"""lot 2 — matos, jetons d'API, saisie de session

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12

Trois ajouts, un seul objet : ramener la saisie d'une session sous les quinze
secondes (cf. PROJET.md §7.2 — le risque du projet est la friction de saisie).

- `gear` — planches et combinaisons. Longueur en mètres : un 6'2 est une unité
  composite, interdite en base (cf. CLAUDE.md).
- `api_tokens` — registre des jetons Bearer longue durée du raccourci iPhone.
  Un JWT ne se révoque pas ; ce registre est ce qui rend la révocation
  possible sans changer `SECRET_KEY`.
- `surf_sessions` — `status`, `gear_id`, `photo_url`, `client_uuid` et
  `start_estimated`. Les sessions déjà en base sont reprises : celles qui
  portent leurs deux notes passent `rated`, les autres `to_rate`.

Une migration = une transaction (cf. CLAUDE.md) : ce fichier ne fait que ce
qu'annonce son titre.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gear",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("gear_type", sa.String(), nullable=False, server_default="board"),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("length_m", sa.Float(), nullable=True),
        sa.Column("volume_l", sa.Float(), nullable=True),
        sa.Column("discipline", sa.String(), nullable=False, server_default="surf"),
        sa.Column("purchased_on", sa.Date(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gear_user_id", "gear", ["user_id"])
    op.create_index("ix_gear_user_active", "gear", ["user_id", "is_active"])

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])
    op.create_index("ix_api_tokens_jti", "api_tokens", ["jti"], unique=True)

    # SQLite ne sait ni ajouter une clé étrangère ni poser une contrainte
    # unique par ALTER : `batch_alter_table` recrée la table sous SQLite et
    # émet de vrais ALTER sous Postgres.
    with op.batch_alter_table("surf_sessions") as batch:
        batch.add_column(
            sa.Column("status", sa.String(), nullable=False, server_default="to_rate")
        )
        batch.add_column(sa.Column("gear_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("photo_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("client_uuid", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column(
                "start_estimated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.create_foreign_key(
            "fk_surf_sessions_gear_id", "gear", ["gear_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_unique_constraint(
            "uq_surf_sessions_client_uuid", ["user_id", "client_uuid"]
        )

    op.create_index(
        "ix_surf_sessions_user_status", "surf_sessions", ["user_id", "status"]
    )

    # Reprise de l'existant : une session porte ses deux notes ou elle est à
    # noter. Le défaut `to_rate` de la colonne a déjà tout marqué à noter, il
    # ne reste qu'à relever celles qui sont complètes.
    op.execute(
        """
        UPDATE surf_sessions
        SET status = 'rated'
        WHERE rating_conditions IS NOT NULL AND rating_personal IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_surf_sessions_user_status", table_name="surf_sessions")

    with op.batch_alter_table("surf_sessions") as batch:
        batch.drop_constraint("uq_surf_sessions_client_uuid", type_="unique")
        batch.drop_constraint("fk_surf_sessions_gear_id", type_="foreignkey")
        batch.drop_column("start_estimated")
        batch.drop_column("client_uuid")
        batch.drop_column("photo_url")
        batch.drop_column("gear_id")
        batch.drop_column("status")

    op.drop_index("ix_api_tokens_jti", table_name="api_tokens")
    op.drop_index("ix_api_tokens_user_id", table_name="api_tokens")
    op.drop_table("api_tokens")

    op.drop_index("ix_gear_user_active", table_name="gear")
    op.drop_index("ix_gear_user_id", table_name="gear")
    op.drop_table("gear")
