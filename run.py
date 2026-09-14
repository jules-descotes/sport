"""Point d'entrée du conteneur.

Les migrations tournent AVANT uvicorn, dans un processus séparé : Alembic est
seul propriétaire du schéma. Créer les tables depuis les métadonnées
SQLAlchemy au démarrage laisserait `alembic_version` vide, et la première
migration du lot 1 échouerait en production sur des tables déjà existantes.

Le démarrage **dit où il va avant d'y aller** : « migration 0017 → 0018 » puis
« OK » ou « ÉCHEC : raison ». Le 14/09, le journal n'annonçait que « Alembic :
upgrade head », et l'échec arrivait sous la forme de quarante lignes de pile
asyncpg dont la cause tenait à la dernière. Savoir de quelle révision on part
et vers laquelle on va est ce qui transforme une panne en diagnostic — et,
quand tout va bien, c'est la trace qui permet de dire après coup quelle
migration est passée à quelle heure.
"""
import asyncio
import logging
import os
import re
import subprocess
import sys

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("run")

HERE = os.path.dirname(os.path.abspath(__file__))


def _head_revision() -> str:
    """La tête du dépôt, lue sans toucher à la base."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config(os.path.join(HERE, "alembic.ini")))
        return script.get_current_head() or "base"
    except Exception as exc:  # noqa: BLE001 — informatif, jamais bloquant
        logger.warning("tête Alembic illisible (%s)", exc)
        return "?"


def _current_revision() -> str:
    """La révision en base, ou « base » si le schéma est vide.

    Le pilote est asynchrone (asyncpg), donc la lecture l'est aussi : ajouter
    psycopg2 aux dépendances pour trois lignes de diagnostic reviendrait à
    embarquer un second pilote Postgres dans l'image.

    Toute erreur est ravalée en « ? ». Une base injoignable est un vrai
    problème, mais c'est `alembic upgrade` qui doit le dire, avec son message
    à lui — pas cette fonction, dont le seul rôle est d'enrichir un journal.
    """
    try:
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings

        async def read() -> str | None:
            engine = create_async_engine(settings.database_url, poolclass=NullPool)
            try:
                async with engine.connect() as connection:
                    return await connection.run_sync(
                        lambda sync: MigrationContext.configure(
                            sync
                        ).get_current_revision()
                    )
            finally:
                await engine.dispose()

        return asyncio.run(read()) or "base"
    except Exception as exc:  # noqa: BLE001 — informatif, jamais bloquant
        logger.warning("révision en base illisible (%s)", exc)
        return "?"


def _reason(result: "subprocess.CompletedProcess[str]") -> str:
    """La ligne qui dit pourquoi, pas les quarante lignes de pile.

    La sortie complète est journalisée juste après ; celle-ci est la ligne
    qu'on lit en premier dans Railway, et il faut qu'elle suffise à savoir
    s'il s'agit d'un type refusé, d'une contrainte violée ou d'une base
    injoignable.
    """
    lines = [
        line.strip() for line in (result.stderr or "").splitlines() if line.strip()
    ]
    for line in reversed(lines):
        # Les exceptions Python se présentent « module.NomError: message ».
        head = line.split(":", 1)[0]
        if head.endswith(("Error", "Exception")) and " " not in head:
            return line
    # Sinon la dernière ligne, débarrassée du préfixe de journalisation
    # d'Alembic : « ERROR [alembic.util.messaging] Can't locate revision… »
    # dit deux fois qu'il s'agit d'une erreur, et une seule fois laquelle.
    last = lines[-1] if lines else f"code de sortie {result.returncode}"
    return re.sub(r"^(ERROR|CRITICAL)\s+\[[^\]]+\]\s*", "", last)


def apply_migrations() -> None:
    current = _current_revision()
    head = _head_revision()

    if current == head:
        logger.info(
            "migration %s → %s : rien à faire, schéma déjà à jour", current, head
        )
    else:
        logger.info("Alembic : migration %s → %s", current, head)

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=HERE,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Le diagnostic AVANT l'arrêt, et sur une seule ligne : un conteneur
        # que Railway relance trois fois produit trois piles identiques, et
        # c'est la ligne de cause qu'on cherche dans les trois.
        logger.error("migration %s → %s : ÉCHEC : %s", current, head, _reason(result))
        logger.error(
            "Alembic — sortie complète :\n%s\n%s", result.stdout, result.stderr
        )
        # Mieux vaut un conteneur qui refuse de démarrer qu'une API servie sur
        # un schéma inconnu.
        raise SystemExit(result.returncode)

    logger.info("migration %s → %s : OK", current, head)
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
