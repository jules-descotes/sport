"""Backfill historique des mesures de la bouée maison.

À lancer **une fois**, à la main, depuis le conteneur Railway. Il remonte le
temps par tranches de douze mois — le maximum qu'accepte `getCampTR.php` — et
il s'arrête tout seul quand le quota du jour est épuisé.

D'où il part, et pourquoi :

- de la **première session enregistrée**, parce que c'est la première ligne
  d'apprentissage à laquelle une mesure pourra se rattacher ;
- de **douze mois en arrière** si la première session est plus ancienne. Au
  delà, on paierait des requêtes pour des mesures qu'aucune session ne viendra
  rejoindre, et le quota est de 150 par jour.

Chaque tranche est écrite avant de passer à la suivante. Un quota épuisé au
milieu n'annule donc rien : on relance le lendemain, et les tranches déjà
écrites repassent en `ON CONFLICT DO NOTHING` sans rien coûter de plus qu'un
appel. Il n'y a rien à reprendre à la main.

`--since` et `--until` bornent la fenêtre à la main (dates ISO, **les deux
incluses**), pour rejouer un trou précis sans repayer toute l'année. Sans
elles : de la première session (ou douze mois en arrière) jusqu'à aujourd'hui.

Usage :
    python -m scripts.backfill_candhis --dry-run
    python -m scripts.backfill_candhis
    python -m scripts.backfill_candhis --since 2026-09-01 --until 2026-09-14
    python -m scripts.backfill_candhis --since 2025-01-01 --station 06402
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, date, datetime, time, timedelta
from typing import Optional, Sequence

from sqlalchemy import func, select

from app.core.config import settings
from app.db.database import async_session
from app.models import load_all_models
from app.models.surf_session import SurfSession
from app.services.calibration import build_pairs
from app.services.candhis import CandhisClient, day_chunks
from app.services.observations import (
    home_station,
    ingest_station_window,
    station_by_code,
)
from app.services.quota import QuotaExhausted, remaining

# Tous les modèles, pas seulement ceux dont ce script parle : SQLAlchemy
# résout les relations écrites en chaîne à la configuration des mappers, et
# un module manquant ne se voit qu'à la première requête (panne du 15/09).
load_all_models()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("backfill_candhis")

PROVIDER = "candhis"
DEFAULT_LOOKBACK_DAYS = 365


async def earliest_start(db) -> Optional[date]:
    result = await db.execute(select(func.min(SurfSession.started_at)))
    value = result.scalar_one_or_none()
    if value is None:
        return None
    moment = value if value.tzinfo else value.replace(tzinfo=UTC)
    return moment.astimezone(UTC).date()


async def run(
    since: Optional[date] = None,
    until: Optional[date] = None,
    station_code: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    if not settings.candhis_enabled:
        logger.error("CANDHIS_API_KEY absente : rien à faire.")
        return 1

    async with async_session() as db:
        if station_code:
            station = await station_by_code(db, station_code)
            # Une station demandée nommément n'est rattachée à aucun spot : on
            # ingère ses mesures, mais on n'apparie rien — une paire de
            # calibration a besoin du point de grille d'un spot en face.
            spot, spot_id = None, None
            if station is None:
                logger.error(
                    "Station %s inconnue — lancer d'abord "
                    "`python -m scripts.import_candhis_stations --zone Z07`",
                    station_code,
                )
                return 1
        else:
            found = await home_station(db)
            if found is None:
                logger.error(
                    "Pas de bouée maison : il faut un spot favori principal et "
                    "une station active à moins de %.0f km.",
                    settings.observation_station_max_km,
                )
                return 1
            station, spot, _distance = found
            spot_id = spot.id

        today = datetime.now(UTC).date()
        floor = today - timedelta(days=DEFAULT_LOOKBACK_DAYS)

        # `--until` borne la fin. Par défaut aujourd'hui : on ne demande pas de
        # mesures au futur, la bouée ne les a pas.
        until = until or today
        if until > today:
            logger.warning(
                "--until %s est dans le futur : ramené à aujourd'hui (%s)",
                until.isoformat(),
                today.isoformat(),
            )
            until = today

        if since is None:
            first = await earliest_start(db)
            # `max` et pas `min` : on ne remonte pas avant douze mois, même si
            # une session rétroactive est plus ancienne. Ces requêtes-là
            # paieraient des mesures que rien ne viendra rejoindre.
            since = max(first, floor) if first is not None else floor
            logger.info(
                "Départ : %s (première session : %s)",
                since.isoformat(),
                first.isoformat() if first else "aucune",
            )

        logger.info(
            "Fenêtre : %s → %s (incluse)", since.isoformat(), until.isoformat()
        )

        if since > until:
            logger.error(
                "Fenêtre vide : --since %s est après --until %s",
                since.isoformat(),
                until.isoformat(),
            )
            return 1

        chunks = day_chunks(since, until)
        left = await remaining(db, PROVIDER, settings.candhis_daily_call_cap)
        logger.info(
            "Bouée %s (%s) : %d tranche(s) de 12 mois, %d appel(s) de quota "
            "restants aujourd'hui",
            station.code,
            station.name,
            len(chunks),
            left,
        )
        for start, end in chunks:
            logger.info("  tranche %s → %s", start.isoformat(), end.isoformat())

        if dry_run:
            logger.info("--dry-run : rien demandé, rien écrit.")
            return 0

        total = 0
        paired = 0
        async with CandhisClient(db) as client:
            for start, end in chunks:
                try:
                    written = await ingest_station_window(
                        db, client, station, [start, end], spot_id=spot_id
                    )
                except QuotaExhausted as exc:
                    logger.warning(
                        "%s — %d mesure(s) écrites, relancer demain : "
                        "les tranches déjà faites ne coûteront rien de plus.",
                        exc,
                        total,
                    )
                    break
                total += written

                if written and spot_id is not None:
                    # On apparie ce qui peut l'être. Sur l'ancien, ce sera peu :
                    # `forecasts` ne remonte pas avant le début de l'ingestion,
                    # et une mesure sans prévision en face ne donne pas de
                    # paire. C'est normal, et c'est pour ça qu'on ne s'alarme
                    # pas d'un backfill qui écrit mille mesures et deux paires.
                    paired += await build_pairs(
                        db,
                        spot,
                        station.code,
                        datetime.combine(start, time.min, tzinfo=UTC),
                        datetime.combine(end, time.max, tzinfo=UTC),
                        distance_m=spot.observation_station_distance_m,
                    )

        logger.info(
            "Backfill terminé : %d mesure(s) écrites, %d paire(s) de calibration",
            total,
            paired,
        )

    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        help="Date de départ AAAA-MM-JJ (défaut : première session, au plus 12 mois)",
    )
    parser.add_argument(
        "--until",
        help="Date de fin AAAA-MM-JJ, **incluse** (défaut : aujourd'hui)",
    )
    parser.add_argument(
        "--station",
        help="Code de campagne à backfiller (défaut : la bouée maison)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Montre les tranches et le quota, sans rien demander ni écrire",
    )
    args = parser.parse_args(argv)

    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None
    return asyncio.run(
        run(
            since=since,
            until=until,
            station_code=args.station,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
