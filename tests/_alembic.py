"""Lancer Alembic pour de vrai, dans un sous-processus.

Deux fichiers de tests en ont besoin — la chaîne (`test_migration_chain`) et
les migrations qui transforment de la donnée (`test_migrations`). Le helper
vit ici plutôt qu'en double : deux copies finiraient par diverger, et c'est
justement la copie non corrigée qui laisserait passer la panne suivante.

Le sous-processus n'est pas un détail. Alembic lit `alembic.ini`, importe
`env.py`, construit son propre moteur : l'appeler en bibliothèque depuis un
test qui a déjà une base en mémoire ne prouve rien sur ce qui tourne dans le
conteneur. Ici, c'est exactement la commande de `run.py`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Joue `alembic <args>` sur `database_url`, sans juger du résultat."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )


def run_alembic(database_url: str, *args: str) -> str:
    """Comme `alembic`, mais un échec fait échouer le test en le racontant."""
    import pytest

    result = alembic(database_url, *args)
    if result.returncode != 0:
        pytest.fail(
            f"alembic {' '.join(args)} a échoué sur {_safe(database_url)} :\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result.stdout + result.stderr


def _safe(url: str) -> str:
    """L'URL sans le mot de passe — un test qui échoue ne le publie pas."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.partition('@')[2]}"
