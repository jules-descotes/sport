"""Ingestion des prévisions — trois niveaux, jamais « tous les spots ».

Le catalogue est mondial, l'ingestion ne l'est pas (cf. PROJET.md §6) :

- **home** — les favoris, vingt au plus. Ingestion planifiée toutes les
  `FORECAST_INGEST_INTERVAL_HOURS` heures. C'est le seul niveau qui capture la
  prévision *au moment où elle est faite* : sans lui, pas de calibration
  prévision ↔ mesure et pas de notification de la veille au soir.
- **potential** — le rayon du profil et les environs de la position courante.
  À la demande, à l'ouverture de l'app, avec un cache de trois heures. Zéro
  appel tant que personne ne regarde.
- **catalog** — le reste du monde. Jamais interrogé.

L'écriture est idempotente (`ON CONFLICT (spot_id, ts, source) DO UPDATE`) :
le conteneur Railway redémarre à froid, le job repart du début, et il ne
duplique jamais une heure déjà ingérée.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import async_session
from app.models.enums import SpotTier
from app.models.forecast import Forecast
from app.models.spot import Spot
from app.services.openmeteo import (
    CallBudget,
    CallBudgetExhausted,
    HourlyBundle,
    OpenMeteoClient,
)

logger = logging.getLogger(__name__)

# Colonnes de données écrasées à chaque rejeu. `spot_id`, `ts` et `source`
# forment la clé et ne sont évidemment pas dedans.
_DATA_COLUMNS = (
    "model",
    "model_version",
    "wave_height_m",
    "wave_direction_deg",
    "wave_period_s",
    "wave_peak_period_s",
    "swell_height_m",
    "swell_direction_deg",
    "swell_period_s",
    "swell_peak_period_s",
    "secondary_swell_height_m",
    "secondary_swell_direction_deg",
    "secondary_swell_period_s",
    "wind_speed_kt",
    "wind_gust_kt",
    "wind_direction_deg",
    "sea_level_m",
    "water_temperature_c",
    "fetched_at",
)

# SQLite plafonne le nombre de paramètres liés d'une requête. Vingt colonnes
# par ligne : cent lignes tiennent partout, et c'est déjà quatre jours.
_CHUNK_SIZE = 100

# Les rafraîchissements détachés (dépassement des 5 s) doivent garder une
# référence vivante, sinon le ramasse-miettes peut annuler la tâche en vol.
_background_tasks: set[asyncio.Task] = set()


def cache_ttl() -> timedelta:
    return timedelta(hours=settings.forecast_cache_hours)


async def upsert_forecast_rows(
    db: AsyncSession,
    spot_id: int,
    bundle: HourlyBundle,
    fetched_at: Optional[datetime] = None,
    source: str = "open-meteo",
) -> int:
    """Écrit les lignes horaires en écrasant les doublons. Renvoie le nombre écrit."""
    rows = bundle.sorted_rows()
    if not rows:
        return 0

    fetched_at = fetched_at or datetime.now(UTC)
    payload = [
        {
            "spot_id": spot_id,
            "ts": ts,
            "source": source,
            "model": settings.forecast_wave_model,
            "model_version": settings.forecast_model_version,
            "fetched_at": fetched_at,
            **values,
        }
        for ts, values in rows
    ]

    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert

    written = 0
    for start in range(0, len(payload), _CHUNK_SIZE):
        chunk = payload[start : start + _CHUNK_SIZE]
        statement = insert(Forecast).values(chunk)
        # Une variable absente d'un chunk ne doit pas écraser par `NULL` une
        # valeur déjà en base : on ne met à jour que ce que le chunk porte.
        present = {
            column
            for column in _DATA_COLUMNS
            if any(column in row for row in chunk)
        }
        statement = statement.on_conflict_do_update(
            index_elements=["spot_id", "ts", "source"],
            set_={column: getattr(statement.excluded, column) for column in present},
        )
        await db.execute(statement)
        written += len(chunk)

    await db.commit()
    return written


async def last_fetched_at(db: AsyncSession, spot_id: int) -> Optional[datetime]:
    result = await db.execute(
        select(func.max(Forecast.fetched_at)).where(Forecast.spot_id == spot_id)
    )
    value = result.scalar_one_or_none()
    if value is None:
        return None
    # SQLite rend des datetimes naïfs : on les recolle en UTC, puisque c'est ce
    # qui a été écrit.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def stale_spot_ids(
    db: AsyncSession, spot_ids: Iterable[int], now: Optional[datetime] = None
) -> list[int]:
    """Spots dont la prévision a plus de trois heures — ou n'existe pas."""
    spot_ids = list(dict.fromkeys(spot_ids))
    if not spot_ids:
        return []

    now = now or datetime.now(UTC)
    result = await db.execute(
        select(Forecast.spot_id, func.max(Forecast.fetched_at))
        .where(Forecast.spot_id.in_(spot_ids))
        .group_by(Forecast.spot_id)
    )
    freshest = {
        spot_id: (value if value.tzinfo else value.replace(tzinfo=UTC))
        for spot_id, value in result.all()
        if value is not None
    }

    ttl = cache_ttl()
    return [
        spot_id
        for spot_id in spot_ids
        if spot_id not in freshest or now - freshest[spot_id] >= ttl
    ]


async def refresh_spots(
    db: AsyncSession,
    spots: Sequence[Spot],
    budget: Optional[CallBudget] = None,
) -> int:
    """Interroge Open-Meteo pour `spots` et écrit le résultat. Renvoie le nombre de spots traités."""
    if not spots:
        return 0

    budget = budget or CallBudget(limit=settings.forecast_call_cap)
    done = 0

    async with OpenMeteoClient(budget=budget) as client:
        for spot in spots:
            try:
                bundle = await client.fetch_forecast(spot.lat, spot.lon)
            except CallBudgetExhausted as exc:
                logger.warning("Ingestion interrompue : %s", exc)
                break
            except Exception as exc:
                # Un spot qui échoue ne doit pas emporter la passe : la mer
                # sera toujours là dans trois heures.
                logger.error(
                    "Prévision indisponible pour %s (%d) : %s", spot.slug, spot.id, exc
                )
                continue

            written = await upsert_forecast_rows(db, spot.id, bundle)
            done += 1
            logger.info("%s : %d heures écrites", spot.slug, written)

    return done


async def refresh_spot_ids_detached(spot_ids: Sequence[int]) -> int:
    """Rafraîchit hors du cycle de vie d'une requête, avec sa propre session.

    Appelée quand Open-Meteo dépasse les cinq secondes : la réponse HTTP est
    déjà partie, la session de la requête est fermée, et ce travail doit
    continuer sans elle.
    """
    if not spot_ids:
        return 0

    async with async_session() as db:
        result = await db.execute(select(Spot).where(Spot.id.in_(list(spot_ids))))
        spots = list(result.scalars().all())
        return await refresh_spots(db, spots)


async def ensure_fresh(
    db: AsyncSession,
    spots: Sequence[Spot],
    timeout_s: Optional[float] = None,
) -> list[int]:
    """Rafraîchit les spots dont le cache a expiré, sans jamais faire attendre.

    On laisse cinq secondes à Open-Meteo. Passé ce délai, on sert ce qu'on a
    en base et le rafraîchissement continue derrière : un écran d'accueil qui
    met huit secondes à répondre ne sera pas ouvert deux fois.
    """
    if not spots:
        return []

    timeout_s = (
        settings.forecast_on_demand_timeout_s if timeout_s is None else timeout_s
    )
    by_id = {spot.id: spot for spot in spots}
    stale = await stale_spot_ids(db, by_id.keys())
    if not stale:
        return []

    task = asyncio.create_task(refresh_spot_ids_detached(stale))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    done, _ = await asyncio.wait({task}, timeout=timeout_s)
    if not done:
        logger.info(
            "Open-Meteo au-delà de %.0f s : %d spot(s) complétés en arrière-plan",
            timeout_s,
            len(stale),
        )
        return stale

    # La tâche a fini : on récolte son éventuelle exception plutôt que de la
    # laisser mourir en silence.
    exception = task.exception()
    if exception is not None:
        logger.error("Rafraîchissement à la demande en échec : %s", exception)
    return []


async def ingest_forecasts() -> None:
    """Passe planifiée : les spots `home`, et eux seuls."""
    async with async_session() as db:
        result = await db.execute(
            select(Spot)
            .where(Spot.tier == SpotTier.HOME.value)
            .order_by(Spot.id)
        )
        spots = list(result.scalars().all())

        if not spots:
            logger.info("forecast_ingest : aucun spot maison, rien à faire")
            return

        budget = CallBudget(limit=settings.forecast_call_cap)
        done = await refresh_spots(db, spots, budget)
        logger.info(
            "forecast_ingest : %d/%d spots, %d appels sur un plafond de %d",
            done,
            len(spots),
            budget.used,
            budget.limit,
        )
