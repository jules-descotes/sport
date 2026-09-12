"""lot 1 — spots, preferences, forecasts, observations, sessions, daily log

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# JSONB en Postgres, JSON en SQLite (tests).
JSON_VARIANT = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def upgrade() -> None:
    op.create_table(
        "spots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column(
            "spot_type", sa.String(), nullable=False, server_default="unknown"
        ),
        sa.Column("source", sa.String(), nullable=False, server_default="osm"),
        sa.Column("osm_type", sa.String(), nullable=True),
        # Les identifiants de nœuds OSM ont dépassé 2^31 : BigInteger obligatoire.
        sa.Column("osm_id", sa.BigInteger(), nullable=True),
        # Orientation calculée depuis le trait de côte OSM, jamais saisie.
        sa.Column("coast_bearing_deg", sa.Float(), nullable=True),
        sa.Column("onshore_dir_deg", sa.Float(), nullable=True),
        sa.Column("coast_distance_m", sa.Float(), nullable=True),
        sa.Column("webcam_url", sa.Text(), nullable=True),
        sa.Column("tier", sa.String(), nullable=False, server_default="catalog"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("osm_tags", JSON_VARIANT, nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        # Clé naturelle de l'import mensuel : rejouable sans jamais dupliquer.
        sa.UniqueConstraint("osm_type", "osm_id", name="uq_spots_osm_object"),
    )
    op.create_index("ix_spots_slug", "spots", ["slug"], unique=True)
    # `/spots/nearby` dégrossit sur une boîte englobante avant le calcul exact :
    # sans cet index, c'est un balayage du catalogue mondial à chaque ouverture.
    op.create_index("ix_spots_lat_lon", "spots", ["lat", "lon"])
    op.create_index("ix_spots_tier", "spots", ["tier"])

    op.create_table(
        "spot_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("radius_km", sa.Float(), nullable=False, server_default="40"),
        sa.Column("home_lat", sa.Float(), nullable=True),
        sa.Column("home_lon", sa.Float(), nullable=True),
        sa.Column("favorite_spot_ids", JSON_VARIANT, nullable=False),
        sa.Column("hidden_spot_ids", JSON_VARIANT, nullable=False),
        sa.Column("last_lat", sa.Float(), nullable=True),
        sa.Column("last_lon", sa.Float(), nullable=True),
        sa.Column("last_position_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_spot_preferences_user_id", "spot_preferences", ["user_id"], unique=True
    )

    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("spot_id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="open-meteo"),
        sa.Column(
            "model", sa.String(), nullable=False, server_default="meteofrance_wave"
        ),
        sa.Column("model_version", sa.String(), nullable=True),
        sa.Column("wave_height_m", sa.Float(), nullable=True),
        sa.Column("wave_direction_deg", sa.Float(), nullable=True),
        sa.Column("wave_period_s", sa.Float(), nullable=True),
        sa.Column("wave_peak_period_s", sa.Float(), nullable=True),
        sa.Column("swell_height_m", sa.Float(), nullable=True),
        sa.Column("swell_direction_deg", sa.Float(), nullable=True),
        sa.Column("swell_period_s", sa.Float(), nullable=True),
        sa.Column("swell_peak_period_s", sa.Float(), nullable=True),
        sa.Column("secondary_swell_height_m", sa.Float(), nullable=True),
        sa.Column("secondary_swell_direction_deg", sa.Float(), nullable=True),
        sa.Column("secondary_swell_period_s", sa.Float(), nullable=True),
        sa.Column("wind_speed_kt", sa.Float(), nullable=True),
        sa.Column("wind_gust_kt", sa.Float(), nullable=True),
        sa.Column("wind_direction_deg", sa.Float(), nullable=True),
        sa.Column("sea_level_m", sa.Float(), nullable=True),
        sa.Column("water_temperature_c", sa.Float(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["spot_id"], ["spots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Le cœur de l'idempotence de l'ingestion.
        sa.UniqueConstraint(
            "spot_id", "ts", "source", name="uq_forecasts_spot_ts_source"
        ),
    )
    op.create_index("ix_forecasts_spot_ts", "forecasts", ["spot_id", "ts"])

    # Table distincte de `forecasts`, et elle le reste : prévision et mesure ne
    # sont pas la même grandeur. Créée vide, remplie au lot 1 bis (CANDHIS).
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("spot_id", sa.Integer(), nullable=True),
        sa.Column("station_id", sa.String(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="candhis"),
        sa.Column("hm0_m", sa.Float(), nullable=True),
        sa.Column("peak_period_s", sa.Float(), nullable=True),
        sa.Column("mean_period_s", sa.Float(), nullable=True),
        sa.Column("wave_direction_deg", sa.Float(), nullable=True),
        sa.Column("wind_speed_kt", sa.Float(), nullable=True),
        sa.Column("wind_gust_kt", sa.Float(), nullable=True),
        sa.Column("wind_direction_deg", sa.Float(), nullable=True),
        sa.Column("water_temperature_c", sa.Float(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["spot_id"], ["spots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id", "ts", "source", name="uq_observations_station_ts_source"
        ),
    )
    op.create_index("ix_observations_spot_ts", "observations", ["spot_id", "ts"])

    op.create_table(
        "surf_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("spot_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        # Discipline sur la session ET sur le matos (cf. CLAUDE.md, règle 8).
        sa.Column("discipline", sa.String(), nullable=False, server_default="surf"),
        # Deux notes distinctes, jamais une seule.
        sa.Column("rating_conditions", sa.Integer(), nullable=True),
        sa.Column("rating_personal", sa.Integer(), nullable=True),
        sa.Column("wave_count", sa.Integer(), nullable=True),
        sa.Column("crowd", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        # Fenêtre T−2 h / T−1 h / T0, volets `forecast` et `observed`.
        sa.Column("conditions_snapshot", JSON_VARIANT, nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spot_id"], ["spots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_surf_sessions_user_id", "surf_sessions", ["user_id"])
    op.create_index("ix_surf_sessions_spot_id", "surf_sessions", ["spot_id"])
    op.create_index(
        "ix_surf_sessions_user_started", "surf_sessions", ["user_id", "started_at"]
    )

    op.create_table(
        "daily_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Date locale et non instant : « le 12 septembre » est une notion humaine.
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("spot_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spot_id"], ["spots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day", name="uq_daily_log_user_day"),
    )
    op.create_index("ix_daily_log_user_id", "daily_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_daily_log_user_id", table_name="daily_log")
    op.drop_table("daily_log")

    op.drop_index("ix_surf_sessions_user_started", table_name="surf_sessions")
    op.drop_index("ix_surf_sessions_spot_id", table_name="surf_sessions")
    op.drop_index("ix_surf_sessions_user_id", table_name="surf_sessions")
    op.drop_table("surf_sessions")

    op.drop_index("ix_observations_spot_ts", table_name="observations")
    op.drop_table("observations")

    op.drop_index("ix_forecasts_spot_ts", table_name="forecasts")
    op.drop_table("forecasts")

    op.drop_index("ix_spot_preferences_user_id", table_name="spot_preferences")
    op.drop_table("spot_preferences")

    op.drop_index("ix_spots_tier", table_name="spots")
    op.drop_index("ix_spots_lat_lon", table_name="spots")
    op.drop_index("ix_spots_slug", table_name="spots")
    op.drop_table("spots")
