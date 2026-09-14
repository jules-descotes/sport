"""Rejoue le volet `observed` des sessions existantes, avec la bouée.

Les sessions enregistrées avant le lot 1 bis portent un volet `observed`
entièrement issu de l'archive Open-Meteo — c'est-à-dire d'un **modèle**. Là où
une bouée a mesuré la même fenêtre, on a maintenant mieux : une mesure.

Ce script ne fait **aucun appel réseau**. Il lit `observations`, déjà en base
grâce au backfill CANDHIS, et recouvre les lignes de houle du snapshot. D'où
l'ordre à respecter :

    1. python -m scripts.import_candhis_stations --zone Z07
    2. python -m scripts.backfill_candhis
    3. python -m scripts.refill_observed        ← ici

L'ancien snapshot n'est **jamais écrasé en silence** : il est empilé dans
`snapshot_history` avec sa raison, comme le fait déjà une correction de spot ou
d'heure. C'est la seule donnée du projet qu'on ne peut pas reconstituer après
coup (règle 7), et un script lancé un soir ne doit pas pouvoir en détruire une
version.

Usage :
    python -m scripts.refill_observed --dry-run
    python -m scripts.refill_observed
    python -m scripts.refill_observed --session 42
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from typing import Optional, Sequence

from sqlalchemy import select

from app.db.database import async_session
from app.models import load_all_models
from app.models.surf_session import SurfSession
from app.services.backfill import window_offsets, window_timestamps
from app.services.observations import station_by_code, station_window_values
from app.services.sessions import archive_snapshot

# Tous les modèles, pas seulement ceux dont ce script parle : SQLAlchemy
# résout les relations écrites en chaîne à la configuration des mappers, et
# un module manquant ne se voit qu'à la première requête (panne du 15/09).
load_all_models()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("refill_observed")


async def run(
    session_id: Optional[int] = None, dry_run: bool = False
) -> int:
    async with async_session() as db:
        query = (
            select(SurfSession)
            .where(SurfSession.deleted_at.is_(None))
            .order_by(SurfSession.started_at)
        )
        if session_id is not None:
            query = query.where(SurfSession.id == session_id)
        sessions = (await db.execute(query)).scalars().all()

        logger.info("%d session(s) à examiner", len(sessions))

        touched = 0
        for session in sessions:
            snapshot = session.conditions_snapshot
            spot = session.spot
            if not snapshot or spot is None:
                continue

            station = await station_by_code(db, spot.observation_station_code)
            if station is None:
                continue

            started = session.started_at
            started = started if started.tzinfo else started.replace(tzinfo=UTC)
            offsets = window_offsets(session.duration_min)
            timestamps = window_timestamps(started, session.duration_min)

            measured = await station_window_values(db, station.code, timestamps)
            if not measured:
                continue

            observed = list(snapshot.get("observed") or [])
            by_offset = {entry.get("offset_h"): entry for entry in observed}

            changed = 0
            for offset, ts in zip(offsets, timestamps):
                overlay = measured.get(ts)
                if not overlay:
                    continue
                entry = by_offset.get(offset)
                if entry is None:
                    # La fenêtre avait un trou d'archive : la bouée le comble,
                    # et la ligne naît directement en « mesurée ».
                    entry = {"offset_h": offset, "ts": ts.isoformat()}
                    observed.append(entry)
                    by_offset[offset] = entry
                if entry.get("wave_source") == "buoy":
                    # Déjà recouverte par un passage précédent : rejouer ne doit
                    # rien réempiler dans l'historique.
                    continue
                entry.update(overlay)
                entry["wave_source"] = "buoy"
                changed += 1

            if not changed:
                continue

            logger.info(
                "  session %s (%s, %s) : %d heure(s) passée(s) à la bouée %s",
                session.id,
                spot.name,
                started.date().isoformat(),
                changed,
                station.code,
            )
            touched += 1

            if dry_run:
                continue

            archive_snapshot(
                session,
                reason="volet observé repris depuis la bouée",
                spot_id=spot.id,
                started_at=started,
            )
            observed.sort(key=lambda entry: entry.get("offset_h", 0))
            updated = dict(snapshot)
            updated["observed"] = observed
            updated["observed_station"] = {
                "code": station.code,
                "name": station.name,
                "distance_m": spot.observation_station_distance_m,
                "source": "candhis",
                "hours": sum(
                    1 for entry in observed if entry.get("wave_source") == "buoy"
                ),
            }
            updated["refilled_at"] = datetime.now(UTC).isoformat()
            # Réassignation et pas mutation : SQLAlchemy ne voit pas la
            # modification d'un dictionnaire JSON en place, et la colonne
            # repartirait inchangée en base.
            session.conditions_snapshot = updated

        if dry_run:
            logger.info("--dry-run : %d session(s) seraient reprises.", touched)
            return 0

        await db.commit()
        logger.info("%d session(s) reprise(s).", touched)

    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=int, help="Ne reprendre que cette session")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Montre ce qui serait repris, sans rien écrire",
    )
    args = parser.parse_args(argv)
    return asyncio.run(run(session_id=args.session, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
