"""lot 4 — training : objectifs mesurés, exercices, formules, séances

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-13

Sept tables, trois idées :

- `objectives` / `objective_measurements` — un objectif se **mesure** ou
  n'existe pas. La valeur de départ n'est pas saisie : c'est la première
  mesure (cf. `app/models/objective.py`).
- `exercises` / `formulas` / `formula_items` — la bibliothèque et les séances
  types. Chaque exercice porte **sa source et sa licence** ; chaque formule
  porte **le principe qui la justifie**, en une ligne.
- `workout_sessions` / `workout_sets` — ce qui a été fait, et une séance
  écourtée y est comptée **à part**. C'est ce qui permettra de corriger une
  formule trop longue au lieu de continuer à la proposer.

Une migration = une transaction (cf. CLAUDE.md) : ce fichier ne fait que ce
qu'annonce son titre. Le contenu — trois objectifs, la bibliothèque
d'exercices, les quinze formules — est **semé par l'application**, pas par la
migration : il évoluera sans qu'on ait à écrire une migration par correction
de tempo.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Objectifs ──────────────────────────────────────────────────────────
    op.create_table(
        "objectives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("measure", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=12), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False, server_default="up"),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column(
            "measure_every_days", sa.Integer(), nullable=False, server_default="21"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("user_id", "slug", name="uq_objectives_user_slug"),
    )
    op.create_index("ix_objectives_user_id", "objectives", ["user_id"])
    op.create_index("ix_objectives_user_active", "objectives", ["user_id", "is_active"])

    op.create_table(
        "objective_measurements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("objective_id", sa.Integer(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["objective_id"], ["objectives.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "objective_id", "measured_on", name="uq_objective_measurement_day"
        ),
    )
    op.create_index(
        "ix_objective_measurements_objective_id",
        "objective_measurements",
        ["objective_id"],
    )

    # ── Bibliothèque et formules ───────────────────────────────────────────
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("name_normalized", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("muscle_group", sa.String(length=40), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="builtin"),
        sa.Column("license", sa.String(length=60), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(length=60), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_exercises_slug"),
    )
    op.create_index("ix_exercises_slug", "exercises", ["slug"])
    op.create_index("ix_exercises_normalized", "exercises", ["name_normalized"])
    op.create_index("ix_exercises_category", "exercises", ["category"])

    op.create_table(
        "formulas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("weekly_target", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("principle", sa.Text(), nullable=False),
        sa.Column("objective_slugs", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("variant_of", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_formulas_slug"),
    )
    op.create_index("ix_formulas_slug", "formulas", ["slug"])
    op.create_index("ix_formulas_family", "formulas", ["variant_of"])

    op.create_table(
        "formula_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("formula_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("tempo", sa.String(length=20), nullable=True),
        sa.Column("rest_s", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["formula_id"], ["formulas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("formula_id", "position", name="uq_formula_item_position"),
    )
    op.create_index("ix_formula_items_formula_id", "formula_items", ["formula_id"])

    # ── Séances ────────────────────────────────────────────────────────────
    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("formula_id", sa.Integer(), nullable=True),
        sa.Column("formula_name", sa.String(length=80), nullable=False),
        sa.Column("formula_family", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cut_short", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("feeling", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["formula_id"], ["formulas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workout_sessions_user_id", "workout_sessions", ["user_id"])
    op.create_index(
        "ix_workout_sessions_user_started", "workout_sessions", ["user_id", "started_at"]
    )

    op.create_table(
        "workout_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workout_session_id", sa.Integer(), nullable=False),
        sa.Column("formula_item_id", sa.Integer(), nullable=True),
        sa.Column("exercise_id", sa.Integer(), nullable=True),
        sa.Column("exercise_name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workout_session_id"], ["workout_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["formula_item_id"], ["formula_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workout_sets_session_id", "workout_sets", ["workout_session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workout_sets_session_id", table_name="workout_sets")
    op.drop_table("workout_sets")

    op.drop_index("ix_workout_sessions_user_started", table_name="workout_sessions")
    op.drop_index("ix_workout_sessions_user_id", table_name="workout_sessions")
    op.drop_table("workout_sessions")

    op.drop_index("ix_formula_items_formula_id", table_name="formula_items")
    op.drop_table("formula_items")

    op.drop_index("ix_formulas_family", table_name="formulas")
    op.drop_index("ix_formulas_slug", table_name="formulas")
    op.drop_table("formulas")

    op.drop_index("ix_exercises_category", table_name="exercises")
    op.drop_index("ix_exercises_normalized", table_name="exercises")
    op.drop_index("ix_exercises_slug", table_name="exercises")
    op.drop_table("exercises")

    op.drop_index(
        "ix_objective_measurements_objective_id", table_name="objective_measurements"
    )
    op.drop_table("objective_measurements")

    op.drop_index("ix_objectives_user_active", table_name="objectives")
    op.drop_index("ix_objectives_user_id", table_name="objectives")
    op.drop_table("objectives")
