"""Types de colonnes partagés.

JSONB en Postgres, JSON en SQLite : le même code de modèle tourne en
production et dans les tests, sans branche conditionnelle.
"""
from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONVariant = JSON().with_variant(JSONB(), "postgresql")
