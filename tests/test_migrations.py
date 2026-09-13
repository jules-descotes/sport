"""Les migrations qui **transforment de la donnée**, jouées sur de vraies lignes.

La plupart des migrations ajoutent une colonne : l'aller-retour se vérifie à
l'œil, et les tests du schéma le couvrent indirectement, puisque toute la suite
tourne sur les métadonnées SQLAlchemy.

Une seule fait autre chose : **0010 double les notes existantes**. Une erreur là
serait silencieuse et définitive — un 4 devenu 4 au lieu de 8 se relirait 2,0,
et toutes les sessions d'avant le 13/09 changeraient de note sans que rien ne
le dise. C'est exactement le genre de chose qu'on ne peut pas rattraper après
coup, comme un `conditions_snapshot` mal figé.

Le test joue donc Alembic **pour de vrai**, dans un sous-processus, sur une base
SQLite jetable semée à la révision précédente.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Deux sessions : une notée 4 / 5, une pas encore notée. La seconde est le cas
# qui casse les migrations écrites trop vite — `NULL * 2` vaut `NULL`, et il
# faut que ça reste `NULL`.
SEED = """
INSERT INTO users (id, email, hashed_password, is_active, created_at)
VALUES (1, 'jules@test', 'x', 1, '2026-09-01T00:00:00');

INSERT INTO spots (id, slug, name, lat, lon, spot_type, source, tier,
                   is_active, is_reference, created_at, updated_at)
VALUES (1, 'graviere', 'La Gravière', 43.66, -1.44, 'beach', 'osm',
        'home', 1, 0, '2026-09-01T00:00:00', '2026-09-01T00:00:00');

INSERT INTO surf_sessions
    (id, user_id, spot_id, started_at, discipline, status,
     rating_conditions, rating_personal, created_at, updated_at)
VALUES
    (1, 1, 1, '2026-09-10T08:00:00', 'surf', 'rated', 4, 5,
     '2026-09-10T08:00:00', '2026-09-10T08:00:00'),
    (2, 1, 1, '2026-09-11T08:00:00', 'surf', 'to_rate', NULL, NULL,
     '2026-09-11T08:00:00', '2026-09-11T08:00:00');
"""


def _alembic(database_url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} a échoué :\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture
def seeded_at_0009(tmp_path: Path) -> tuple[str, Path]:
    """Une base à la révision 0009, avec deux sessions notées à l'ancienne."""
    db_path = tmp_path / "migration.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    _alembic(url, "upgrade", "0009")

    connection = sqlite3.connect(db_path)
    connection.executescript(SEED)
    connection.commit()
    connection.close()

    return url, db_path


def _columns(db_path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(db_path)
    names = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    connection.close()
    return names


def _rows(db_path: Path, query: str) -> list[tuple]:
    connection = sqlite3.connect(db_path)
    rows = connection.execute(query).fetchall()
    connection.close()
    return rows


def test_0010_doubles_the_existing_ratings(seeded_at_0009) -> None:
    """Un 4 devient 8, et se relit 4,0. L'historique d'apprentissage est intact."""
    url, db_path = seeded_at_0009

    _alembic(url, "upgrade", "0010")

    assert _rows(
        db_path,
        "SELECT id, rating_conditions_half, rating_personal_half "
        "FROM surf_sessions ORDER BY id",
    ) == [(1, 8, 10), (2, None, None)]


def test_0010_leaves_unrated_sessions_unrated(seeded_at_0009) -> None:
    """`NULL × 2` doit rester `NULL`.

    Une session à noter qui ressortirait à 0 serait comptée comme une session
    exécrable par toutes les statistiques, et elle sortirait de l'écran Jour
    sans jamais avoir été notée.
    """
    url, db_path = seeded_at_0009
    _alembic(url, "upgrade", "0010")

    assert _rows(
        db_path,
        "SELECT status FROM surf_sessions WHERE rating_conditions_half IS NULL",
    ) == [("to_rate",)]


def test_0010_removes_the_old_columns(seeded_at_0009) -> None:
    """Les garder « au cas où » laisserait deux vérités pour la même note, et
    la seconde serait périmée dès la première notation."""
    url, db_path = seeded_at_0009
    _alembic(url, "upgrade", "0010")

    columns = _columns(db_path, "surf_sessions")
    assert "rating_conditions" not in columns
    assert "rating_conditions_half" in columns


def test_0010_can_be_rolled_back(seeded_at_0009) -> None:
    """La descente divise. Un 3,5 saisi entre-temps redevient 3 : c'est la
    seule perte possible, et elle est assumée — revenir en arrière veut dire
    revenir à une échelle qui n'a pas de demi-point."""
    url, db_path = seeded_at_0009
    _alembic(url, "upgrade", "0010")
    _alembic(url, "downgrade", "0009")

    assert _rows(
        db_path,
        "SELECT id, rating_conditions, rating_personal FROM surf_sessions ORDER BY id",
    ) == [(1, 4, 5), (2, None, None)]


def test_every_migration_runs_forward_and_back(tmp_path: Path) -> None:
    """L'aller-retour complet, de rien à la tête et retour.

    Le garde-fou le moins coûteux du projet : une migration dont le
    `downgrade` est faux ne se découvre autrement qu'un soir de panne, au
    moment où l'on en a le plus besoin.
    """
    db_path = tmp_path / "roundtrip.db"
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    _alembic(url, "upgrade", "head")
    _alembic(url, "downgrade", "base")
    _alembic(url, "upgrade", "head")
