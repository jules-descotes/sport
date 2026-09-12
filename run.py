"""Point d'entrée du conteneur.

Les migrations tournent AVANT uvicorn, dans un processus séparé : Alembic est
seul propriétaire du schéma. Créer les tables depuis les métadonnées
SQLAlchemy au démarrage laisserait `alembic_version` vide, et la première
migration du lot 1 échouerait en production sur des tables déjà existantes.
"""
import logging
import os
import subprocess
import sys

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("run")


def apply_migrations() -> None:
    logger.info("Alembic : upgrade head")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Mieux vaut un conteneur qui refuse de démarrer qu'une API servie sur
        # un schéma inconnu. Railway relance trois fois (railway.json).
        logger.error("Alembic a échoué :\n%s\n%s", result.stdout, result.stderr)
        raise SystemExit(result.returncode)
    logger.info("Alembic : schéma à jour")


if __name__ == "__main__":
    apply_migrations()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
