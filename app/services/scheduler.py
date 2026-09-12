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
from app.services.forecast_ingest import ingest_forecasts

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _forecast_ingest_job() -> None:
    try:
        await ingest_forecasts()
    except Exception as exc:  # le job ne doit jamais tuer l'ordonnanceur
        logger.error("forecast_ingest a échoué : %s", exc, exc_info=True)


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
    _scheduler.start()
    logger.info(
        "Ordonnanceur démarré : forecast_ingest toutes les %d h",
        settings.forecast_ingest_interval_hours,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
