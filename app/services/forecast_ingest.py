"""Ingestion des prévisions de houle et de vent — coquille du lot 0.

Le contenu arrive au lot 1 : Open-Meteo Marine (modèle MFWAM explicitement
sélectionné) pour `forecasts`, CANDHIS pour `observations`. Deux tables
distinctes : prévision et mesure ne sont pas la même grandeur.

Contrainte de conception à tenir dès la première ligne de code réelle :
l'écriture doit être idempotente (`ON CONFLICT DO UPDATE` sur
`(spot_id, ts, source)`). Le conteneur Railway redémarre à froid, le job
repart du début, et il ne doit jamais dupliquer une heure déjà ingérée.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def ingest_forecasts() -> None:
    logger.info("forecast_ingest : rien à faire (implémentation au lot 1)")
