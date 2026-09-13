"""lot 5 (13/09) — demi-points sur les notes, et segments horaires

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-13

Deux retours d'usage après deux jours en ligne, et ils tiennent ensemble.

**Les demi-points.** « 3 ou 4 » ne suffisait pas à départager deux sessions
d'une même semaine. L'échelle passe donc de cinq à dix crans, et les colonnes
portent `note × 2` — 7 pour 3,5.

Elles sont **renommées** au passage : `rating_conditions` devient
`rating_conditions_half`. Ce n'est pas de la coquetterie. Une colonne qui
change d'unité sans changer de nom est une bombe à retardement : la première
requête écrite de mémoire lirait un 8 comme un 8/5, et rien ne le signalerait.
Le suffixe rend l'unité impossible à confondre, comme `_m`, `_s` et `_kt`
ailleurs dans le schéma.

La conversion des lignes existantes est un simple doublement : une note de 4
devient 8, et elle se relit 4,0. Aucune donnée n'est perdue, et la migration
descendante divise — au prix des demi-points saisis entre-temps, ce que son
commentaire dit.

**Les segments.** Une session de deux heures et demie n'est pas une note : la
houle monte, le vent se lève, la marée tourne. Chaque segment porte une **heure
pleine**, ce qui lui permet de s'apparier à sa ligne horaire du
`conditions_snapshot` — et c'est ce qui en fait un point d'apprentissage à part
entière plutôt qu'un détail d'affichage.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Les nouvelles colonnes, vides.
    with op.batch_alter_table("surf_sessions") as batch:
        batch.add_column(sa.Column("rating_conditions_half", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("rating_personal_half", sa.Integer(), nullable=True))

    # 2. Les notes existantes, doublées. Une note de 4 devient 8 et se relit
    #    4,0 : l'historique d'apprentissage est conservé tel quel.
    op.execute(
        "UPDATE surf_sessions "
        "SET rating_conditions_half = rating_conditions * 2, "
        "    rating_personal_half = rating_personal * 2"
    )

    # 3. Les anciennes colonnes partent. Les garder « au cas où » laisserait
    #    deux vérités pour la même note, et la seconde serait périmée dès la
    #    première notation.
    with op.batch_alter_table("surf_sessions") as batch:
        batch.drop_column("rating_conditions")
        batch.drop_column("rating_personal")

    op.create_table(
        "session_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("surf_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rating_conditions_half", sa.Integer(), nullable=True),
        sa.Column("rating_personal_half", sa.Integer(), nullable=True),
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
            "session_id", "started_at", name="uq_session_segments_session_hour"
        ),
    )
    op.create_index(
        "ix_session_segments_session_id", "session_segments", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_segments_session_id", table_name="session_segments")
    op.drop_table("session_segments")

    with op.batch_alter_table("surf_sessions") as batch:
        batch.add_column(sa.Column("rating_conditions", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("rating_personal", sa.Integer(), nullable=True))

    # Division entière : un 3,5 saisi depuis la montée redevient 3. C'est la
    # seule perte possible de cette migration, et elle est assumée — revenir en
    # arrière veut dire revenir à une échelle qui n'a pas de demi-point.
    op.execute(
        "UPDATE surf_sessions "
        "SET rating_conditions = rating_conditions_half / 2, "
        "    rating_personal = rating_personal_half / 2"
    )

    with op.batch_alter_table("surf_sessions") as batch:
        batch.drop_column("rating_personal_half")
        batch.drop_column("rating_conditions_half")
