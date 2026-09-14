"""Ordonnanceur in-process, dans la boucle d'événements de FastAPI.

Pas de cron externe ni de service supplémentaire : Railway fait tourner un
worker unique, l'ordonnanceur vit dans le conteneur. Si on passe un jour à
plusieurs instances, il faudra un worker dédié — les jobs ne sont pas
verrouillés entre processus.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.db.database import async_session
from app.services.forecast_ingest import ingest_forecasts
from app.services.observations import ingest_home_observations
from app.services.sessions import purge_trashed_sessions

logger = logging.getLogger(__name__)

# La corbeille se vide une fois par jour. Elle retient trente jours : une passe
# quotidienne suffit largement, et une passe par cycle d'ingestion ferait
# vingt-quatre requêtes de suppression par jour pour rien.
TRASH_PURGE_INTERVAL_HOURS = 24

_scheduler: AsyncIOScheduler | None = None


async def _forecast_ingest_job() -> None:
    try:
        await ingest_forecasts()
    except Exception as exc:  # le job ne doit jamais tuer l'ordonnanceur
        logger.error("forecast_ingest a échoué : %s", exc, exc_info=True)


async def _observation_ingest_job() -> None:
    """Les mesures de la bouée maison, toutes les heures.

    Une passe couvre les trois dernières heures et n'écrit qu'un appel au
    compteur : ~24 par jour, loin sous le plafond de 140. Trois heures et pas
    une : le recouvrement est ce qui rattrape la passe manquée pendant un
    redéploiement, et `ON CONFLICT DO NOTHING` le rend gratuit.
    """
    try:
        async with async_session() as session:
            await ingest_home_observations(session)
    except Exception as exc:  # le job ne doit jamais tuer l'ordonnanceur
        logger.error("ingestion des bouées échouée : %s", exc, exc_info=True)


async def _trash_purge_job() -> None:
    """Détruit ce que la corbeille garde depuis plus de trente jours.

    C'est un job et pas une requête de lecture : une lecture qui écrit est une
    surprise, et celle-ci détruirait des lignes d'apprentissage.
    """
    try:
        async with async_session() as session:
            await purge_trashed_sessions(session)
    except Exception as exc:
        logger.error("purge de la corbeille échouée : %s", exc, exc_info=True)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _forecast_ingest_job,
        IntervalTrigger(hours=settings.forecast_ingest_interval_hours),
        id="forecast_ingest",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        _trash_purge_job,
        IntervalTrigger(hours=TRASH_PURGE_INTERVAL_HOURS),
        id="trash_purge",
        max_instances=1,
        coalesce=True,
    )

    # Le job des bouées n'est **pas déclaré** sans clé, plutôt que déclaré et
    # inerte : un job qui tourne toutes les heures pour ne rien faire remplit
    # les journaux Railway de lignes qui n'apprennent rien, et finit par cacher
    # celles qui comptent.
    if settings.candhis_enabled:
        _scheduler.add_job(
            _observation_ingest_job,
            IntervalTrigger(hours=settings.candhis_ingest_interval_hours),
            id="observation_ingest",
            max_instances=1,
            coalesce=True,
        )

    _scheduler.start()
    logger.info(
        "Ordonnanceur démarré : forecast_ingest toutes les %d h, "
        "purge de la corbeille toutes les %d h, bouées %s",
        settings.forecast_ingest_interval_hours,
        TRASH_PURGE_INTERVAL_HOURS,
        f"toutes les {settings.candhis_ingest_interval_hours} h"
        if settings.candhis_enabled
        else "désactivées (pas de clé)",
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
