"""lot 1 ter — `run_ts` dans la clé de `forecasts`

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12

Historiser les runs de prévision. Sans `run_ts` dans la clé, la passe du matin
écrase la prévision émise la veille au soir : ni l'écart « depuis hier soir »
ni la calibration prévision ↔ mesure ne sont possibles, et chaque jour
d'ingestion passé sans lui est perdu définitivement (cf. PROJET.md §7.3).

Les lignes déjà en base reçoivent `run_ts = fetched_at` : c'est exactement ce
que `fetched_at` portait jusqu'ici — l'heure à laquelle la prévision a été
captée. L'historique existant devient donc un run unique par ligne, ce qui est
la vérité : avant cette migration, il n'y en avait qu'un.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable d'abord : la colonne doit exister avant d'être remplie.
    op.add_column(
        "forecasts", sa.Column("run_ts", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE forecasts SET run_ts = fetched_at WHERE run_ts IS NULL")

    # `batch_alter_table` recrée la table sous SQLite (qui ne sait pas lâcher
    # une contrainte) et émet de vrais ALTER sous Postgres. Les deux passages
    # sont séparés : SQLite refuse de poser NOT NULL et de changer la clé dans
    # la même recréation sans repasser par une table intermédiaire propre.
    with op.batch_alter_table("forecasts") as batch:
        batch.alter_column(
            "run_ts", existing_type=sa.DateTime(timezone=True), nullable=False
        )

    with op.batch_alter_table("forecasts") as batch:
        batch.drop_constraint("uq_forecasts_spot_ts_source", type_="unique")
        batch.create_unique_constraint(
            "uq_forecasts_spot_ts_source_run",
            ["spot_id", "ts", "source", "run_ts"],
        )


def downgrade() -> None:
    # Revenir en arrière écrase l'historique des runs : on ne garde que le plus
    # récent par (spot, heure, source), sinon la contrainte d'origine ne peut
    # pas être reposée.
    op.execute(
        """
        DELETE FROM forecasts
        WHERE id NOT IN (
            SELECT MAX(id) FROM forecasts GROUP BY spot_id, ts, source
        )
        """
    )

    with op.batch_alter_table("forecasts") as batch:
        batch.drop_constraint("uq_forecasts_spot_ts_source_run", type_="unique")
        batch.create_unique_constraint(
            "uq_forecasts_spot_ts_source", ["spot_id", "ts", "source"]
        )
        batch.drop_column("run_ts")
