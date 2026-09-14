"""15/09 — les bouées : catalogue des stations, rattachement, mesures enrichies

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-15

Trois choses, et elles ne valent qu'ensemble.

**`observation_stations`** — le catalogue des houlographes CANDHIS. Une station
n'est pas un spot : un spot est un endroit où l'on surfe, une station est un
instrument au large. Clé naturelle `code` (le numéro de campagne, `06402` pour
Anglet), rejouable et idempotent comme l'import OSM.

`code` est une **chaîne** et pas un entier : les codes commencent par un zéro,
et `06402` deviendrait `6402` au premier aller-retour.

**Le rattachement, porté par le spot** — `observation_station_code` et
`observation_station_distance_m`. Il vit sur le spot parce que c'est le spot
qui a besoin de savoir qui le mesure, et la distance est stockée parce qu'elle
s'affiche (« bouée d'Anglet, 4 km ») : une distance recalculée à chaque rendu
serait trois lignes de trigonométrie pour une valeur qui ne bouge jamais.

**`observations` s'enrichit** — l'étalement directionnel, la hauteur maximale,
la ligne brute et la version de format. `raw` garde la ligne entière appariée à
son en-tête : le jour où on voudra une colonne qu'on n'a pas su lire, elle sera
là, et il n'y aura pas à redemander douze mois d'archive à une API qui en
accorde 150 par jour.

`format_version` porte le type de houlographe reconnu — même principe que
`model_version` sur `forecasts`. Le jour où le Cerema ajoute une colonne,
l'historique dira dans quelle grammaire il a été écrit.

> Booléens en `sa.false()`, jamais `sa.text("0")` — c'est exactement ce qui a
> mis la production à terre le 14/09.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# JSONB en Postgres, JSON en SQLite — le même choix que `app/db/types.py`.
JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "observation_stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="candhis"),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("depth_m", sa.Float(), nullable=True),
        sa.Column("sensor", sa.String(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_directional", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("houlographe_type", sa.String(), nullable=True),
        sa.Column("data_type", sa.String(), nullable=True),
        sa.Column("last_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_observation_stations_code"),
    )
    op.create_index(
        "ix_observation_stations_code", "observation_stations", ["code"]
    )
    op.create_index(
        "ix_observation_stations_lat_lon", "observation_stations", ["lat", "lon"]
    )

    with op.batch_alter_table("spots") as batch:
        batch.add_column(
            sa.Column("observation_station_code", sa.String(), nullable=True)
        )
        batch.add_column(
            sa.Column("observation_station_distance_m", sa.Float(), nullable=True)
        )

    with op.batch_alter_table("observations") as batch:
        batch.add_column(sa.Column("wave_height_max_m", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column("directional_spread_deg", sa.Float(), nullable=True)
        )
        batch.add_column(sa.Column("raw", JSON_VARIANT, nullable=True))
        batch.add_column(sa.Column("format_version", sa.String(), nullable=True))

    # Lecture type du bloc « Maintenant » : la dernière mesure de cette station.
    op.create_index(
        "ix_observations_station_ts", "observations", ["station_id", "ts"]
    )


def downgrade() -> None:
    op.drop_index("ix_observations_station_ts", table_name="observations")

    with op.batch_alter_table("observations") as batch:
        batch.drop_column("format_version")
        batch.drop_column("raw")
        batch.drop_column("directional_spread_deg")
        batch.drop_column("wave_height_max_m")

    with op.batch_alter_table("spots") as batch:
        batch.drop_column("observation_station_distance_m")
        batch.drop_column("observation_station_code")

    op.drop_index(
        "ix_observation_stations_lat_lon", table_name="observation_stations"
    )
    op.drop_index("ix_observation_stations_code", table_name="observation_stations")
    op.drop_table("observation_stations")
