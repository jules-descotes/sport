"""Les mesures de bouée — rattachement, ingestion, lecture.

Trois responsabilités, et une règle qui les traverse : **`observations` ne
contient que du mesuré**. Pas une valeur de prévision n'y entre, jamais, même
pour boucher un trou. C'est la règle 9 du cadrage, et c'est ce qui permettra au
lot 6 de comparer les deux sans se mentir (cf. PROJET.md §7.1).

1. **Rattachement** — chaque spot reçoit la station la plus proche et sa
   distance, et *aucune* au-delà de 30 km. Ce n'est pas une pudeur de
   précision : à 40 km au large, une houle mesurée décrit une autre mer, et
   l'appeler « les conditions du spot » serait une erreur d'étiquette dans la
   donnée d'apprentissage.
2. **Ingestion** — une passe horaire sur la station maison, idempotente sur
   `(station, ts, source)`.
3. **Lecture** — la dernière mesure, et la fenêtre d'une session.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.forecast import Observation
from app.models.observation_station import ObservationStation
from app.models.profile import Profile
from app.models.spot import Spot
from app.services.candhis import (
    CandhisClient,
    CandhisDisabled,
    CandhisError,
    Measurement,
)
from app.services.geo import haversine_m
from app.services.quota import QuotaExhausted

logger = logging.getLogger(__name__)

SOURCE = "candhis"

# Les colonnes de mesure d'`observations`, dans l'ordre où on les lit.
MEASUREMENT_FIELDS = (
    "hm0_m",
    "wave_height_max_m",
    "peak_period_s",
    "mean_period_s",
    "wave_direction_deg",
    "directional_spread_deg",
    "water_temperature_c",
)

# Libellé de format, écrit sur chaque ligne — cf. `format_version`.
FORMAT_BY_TYPE = {
    "0": "tr-non-directionnel-h13",
    "1": "tr-directionnel-hm0",
    "2": "tr-directionnel-h13",
}

_CHUNK_SIZE = 500


# --- Rattachement ---------------------------------------------------------


def max_distance_m() -> float:
    return settings.observation_station_max_km * 1000.0


async def nearest_station(
    db: AsyncSession,
    lat: float,
    lon: float,
    active_only: bool = True,
    max_m: Optional[float] = None,
) -> Optional[tuple[ObservationStation, float]]:
    """La station la plus proche, et sa distance — ou rien.

    `active_only` par défaut : une bouée à l'arrêt est plus proche qu'une bouée
    vivante dans exactement le cas qui nous intéresse, et lui rattacher un spot
    donnerait un bloc « Maintenant » perpétuellement vide.
    """
    limit = max_distance_m() if max_m is None else max_m

    query = select(ObservationStation)
    if active_only:
        query = query.where(ObservationStation.is_active.is_(True))
    stations = (await db.execute(query)).scalars().all()

    best: Optional[tuple[ObservationStation, float]] = None
    for station in stations:
        distance = haversine_m(lat, lon, station.lat, station.lon)
        if distance > limit:
            continue
        if best is None or distance < best[1]:
            best = (station, distance)
    return best


async def link_spots_to_stations(
    db: AsyncSession, spot_ids: Optional[Sequence[int]] = None
) -> int:
    """Réaffecte la station la plus proche à des spots — ou à tout le catalogue.

    Idempotent, et rejouable après chaque import de stations. Un spot hors
    portée est **remis à `NULL`** plutôt que laissé avec son ancienne station :
    une bouée retirée du réseau ne doit pas continuer à s'afficher sur un spot
    qu'elle ne mesure plus.
    """
    stations = (
        (await db.execute(select(ObservationStation).where(
            ObservationStation.is_active.is_(True)
        )))
        .scalars()
        .all()
    )

    query = select(Spot)
    if spot_ids is not None:
        if not spot_ids:
            return 0
        query = query.where(Spot.id.in_(list(spot_ids)))
    spots = (await db.execute(query)).scalars().all()

    limit = max_distance_m()
    changed = 0
    for spot in spots:
        best_code: Optional[str] = None
        best_distance: Optional[float] = None
        for station in stations:
            distance = haversine_m(spot.lat, spot.lon, station.lat, station.lon)
            if distance > limit:
                continue
            if best_distance is None or distance < best_distance:
                best_code, best_distance = station.code, distance

        rounded = None if best_distance is None else round(best_distance, 1)
        if (
            spot.observation_station_code != best_code
            or spot.observation_station_distance_m != rounded
        ):
            spot.observation_station_code = best_code
            spot.observation_station_distance_m = rounded
            changed += 1

    await db.commit()
    logger.info(
        "Rattachement bouées : %d spot(s) modifié(s) sur %d, %d station(s) active(s)",
        changed,
        len(spots),
        len(stations),
    )
    return changed


async def station_by_code(
    db: AsyncSession, code: Optional[str]
) -> Optional[ObservationStation]:
    if not code:
        return None
    result = await db.execute(
        select(ObservationStation).where(ObservationStation.code == code)
    )
    return result.scalar_one_or_none()


async def home_spot(db: AsyncSession) -> Optional[Spot]:
    """Le spot favori principal — l'application n'a qu'un utilisateur.

    On passe par le profil plutôt que par un identifiant d'utilisateur : le job
    planifié n'a pas de requête, donc pas d'utilisateur courant.
    """
    result = await db.execute(
        select(Spot)
        .join(Profile, Profile.home_spot_id == Spot.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def home_station(
    db: AsyncSession,
) -> Optional[tuple[ObservationStation, Spot, float]]:
    """La bouée maison : celle du favori principal, si elle est assez proche.

    Elle n'est **jamais écrite en dur** (cf. docs/CANDHIS.md §7) : elle se
    déduit du favori et de l'état du réseau. Une bouée qui part en carénage
    sort d'elle-même, sans redéploiement.
    """
    spot = await home_spot(db)
    if spot is None:
        return None

    station = await station_by_code(db, spot.observation_station_code)
    if station is not None and station.is_active:
        distance = spot.observation_station_distance_m
        if distance is None:
            distance = haversine_m(spot.lat, spot.lon, station.lat, station.lon)
        return station, spot, distance

    # Le rattachement n'a pas encore tourné, ou il date d'avant cet import.
    found = await nearest_station(db, spot.lat, spot.lon)
    if found is None:
        return None
    station, distance = found
    return station, spot, distance


# --- Écriture -------------------------------------------------------------


def _row(
    measurement: Measurement,
    station_code: str,
    spot_id: Optional[int],
    format_version: Optional[str],
    fetched_at: datetime,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "station_id": station_code,
        "spot_id": spot_id,
        "ts": measurement.ts,
        "source": SOURCE,
        "raw": measurement.raw,
        "format_version": format_version,
        "fetched_at": fetched_at,
    }
    for field in MEASUREMENT_FIELDS:
        row[field] = measurement.values.get(field)
    return row


async def store_measurements(
    db: AsyncSession,
    station: ObservationStation,
    measurements: Iterable[Measurement],
    spot_id: Optional[int] = None,
    fetched_at: Optional[datetime] = None,
) -> int:
    """Écrit des mesures, `ON CONFLICT DO NOTHING` sur `(station, ts, source)`.

    « DO NOTHING » et pas « DO UPDATE » : une mesure est un constat, et un
    constat ne se corrige pas d'une passe à l'autre. Rejouer le job vingt fois
    dans l'heure ne change donc rien — ce qui est exactement ce qu'on veut d'un
    conteneur qui redémarre.

    Les lignes entièrement vides sont écartées : une bouée en avarie émet son
    horodatage et des 999.9999 partout, et les écrire remplirait la table de
    lignes que la calibration devrait ensuite apprendre à ignorer.
    """
    fetched_at = fetched_at or datetime.now(UTC)
    format_version = FORMAT_BY_TYPE.get(station.houlographe_type or "")

    payload = [
        _row(measurement, station.code, spot_id, format_version, fetched_at)
        for measurement in measurements
        if not measurement.is_empty
    ]
    if not payload:
        return 0

    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert

    for start in range(0, len(payload), _CHUNK_SIZE):
        chunk = payload[start : start + _CHUNK_SIZE]
        statement = insert(Observation).values(chunk).on_conflict_do_nothing(
            index_elements=["station_id", "ts", "source"]
        )
        await db.execute(statement)

    latest = max(row["ts"] for row in payload)
    await db.execute(
        update(ObservationStation)
        .where(ObservationStation.id == station.id)
        .where(
            (ObservationStation.last_measured_at.is_(None))
            | (ObservationStation.last_measured_at < latest)
        )
        .values(last_measured_at=latest)
    )

    await db.commit()
    return len(payload)


# --- Ingestion ------------------------------------------------------------

# La fenêtre du job horaire. On demande la journée à l'API — sa granularité est
# le jour, pas l'heure (cf. docs/CANDHIS.md §4.6) — et on garde les trois
# dernières heures. Deux journées seulement quand la fenêtre franchit minuit :
# une passe à 00 h 30 doit rattraper la fin de la veille, pas la perdre.
INGEST_WINDOW_HOURS = 3


def ingest_days(now: datetime, window_hours: int = INGEST_WINDOW_HOURS) -> list[date]:
    now = now.astimezone(UTC)
    start = now - timedelta(hours=window_hours)
    days = {start.date(), now.date()}
    return sorted(days)


async def ingest_station_window(
    db: AsyncSession,
    client: CandhisClient,
    station: ObservationStation,
    days: Sequence[date],
    spot_id: Optional[int] = None,
    since: Optional[datetime] = None,
) -> int:
    """Une passe sur une station, sur les journées données.

    Un échec — réseau, format inattendu, quota — est **journalisé et rendu**,
    jamais levé : la passe suivante réessaiera, et une bouée muette ne doit pas
    faire tomber l'ordonnanceur.
    """
    if not days:
        return 0

    try:
        measurements = await client.real_time(station.code, days[0], days[-1])
    except CandhisDisabled:
        return 0
    except QuotaExhausted as exc:
        logger.warning("Ingestion bouée %s abandonnée : %s", station.code, exc)
        return 0
    except CandhisError as exc:
        # `success=False` en fait partie : « pas de données pour cette
        # campagne » est une réponse, pas une panne.
        logger.warning("CANDHIS a refusé %s : %s", station.code, exc)
        return 0
    except Exception as exc:  # réseau, JSON, tout le reste
        logger.error(
            "Ingestion bouée %s impossible : %s", station.code, exc, exc_info=True
        )
        return 0

    if since is not None:
        measurements = [m for m in measurements if m.ts >= since]

    written = await store_measurements(db, station, measurements, spot_id=spot_id)
    logger.info(
        "Bouée %s (%s) : %d mesure(s) retenue(s) sur %s",
        station.code,
        station.name,
        written,
        " → ".join(day.isoformat() for day in (days[0], days[-1])),
    )
    return written


async def ingest_home_observations(db: AsyncSession) -> int:
    """La passe horaire — la station maison, les trois dernières heures.

    Ne fait rien, en le disant une fois, quand il n'y a pas de clé, pas de
    favori, ou pas de bouée assez proche. Aucun de ces trois cas n'est une
    panne.
    """
    if not settings.candhis_enabled:
        return 0

    found = await home_station(db)
    if found is None:
        logger.info(
            "Pas de bouée maison : ni favori principal, ni station active à "
            "moins de %.0f km. Rien à ingérer.",
            settings.observation_station_max_km,
        )
        return 0

    station, spot, distance = found
    now = datetime.now(UTC)
    since = now - timedelta(hours=INGEST_WINDOW_HOURS)

    async with CandhisClient(db) as client:
        written = await ingest_station_window(
            db,
            client,
            station,
            ingest_days(now),
            spot_id=spot.id,
            since=since,
        )

    return written


# --- Lecture --------------------------------------------------------------


async def latest_observation(
    db: AsyncSession, station_code: str
) -> Optional[Observation]:
    result = await db.execute(
        select(Observation)
        .where(Observation.station_id == station_code)
        .where(Observation.source == SOURCE)
        .order_by(Observation.ts.desc())
        .limit(1)
    )
    observation = result.scalar_one_or_none()
    if observation is not None and observation.ts.tzinfo is None:
        # SQLite rend des datetimes naïfs ; on recolle UTC, qui est ce qui a
        # été écrit (cf. `app/schemas/types.py`).
        observation.ts = observation.ts.replace(tzinfo=UTC)
    return observation


async def observations_between(
    db: AsyncSession,
    station_code: str,
    start: datetime,
    end: datetime,
) -> list[Observation]:
    result = await db.execute(
        select(Observation)
        .where(Observation.station_id == station_code)
        .where(Observation.source == SOURCE)
        .where(Observation.ts >= start)
        .where(Observation.ts <= end)
        .order_by(Observation.ts)
    )
    rows = list(result.scalars().all())
    for row in rows:
        if row.ts.tzinfo is None:
            row.ts = row.ts.replace(tzinfo=UTC)
    return rows
