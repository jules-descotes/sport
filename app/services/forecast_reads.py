"""Lecture de `forecasts` — le dernier run, et l'écart depuis la veille au soir.

Depuis que `run_ts` est dans la clé, une heure donnée d'un spot porte **autant
de lignes que de passes d'ingestion**. Toute lecture qui se veut « la prévision
actuelle » doit donc trancher, et elle tranche toujours de la même façon : le
`run_ts` maximum par `(spot_id, ts, source)`.

Ce module est le seul endroit où cette règle est écrite. Les routes, la reco et
le backfill passent par lui — une lecture qui oublierait le filtre rendrait
cinq valeurs pour une heure, et l'écran afficherait la première venue.

L'intérêt de l'historisation, lui, est dans `forecast_delta` : « la houle de
demain matin est annoncée 30 cm plus haute qu'hier soir » n'est calculable
qu'à partir du moment où l'on garde les deux runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.forecast import Forecast
from app.models.spot import Spot

DEFAULT_SOURCE = "open-meteo"

# « La veille au soir », heure locale. C'est l'heure de la dernière passe qu'on
# a regardée avant de se coucher, et le point de comparaison naturel du matin :
# la question posée est « qu'est-ce qui a changé depuis hier soir ? ».
EVENING_HOUR = 20

# Grandeurs comparées entre deux runs. Les directions sont traitées à part :
# l'écart entre 350° et 10° vaut +20°, pas −340°.
DELTA_FIELDS = (
    "wave_height_m",
    "wave_period_s",
    "swell_height_m",
    "swell_period_s",
    "wind_speed_kt",
    "wind_gust_kt",
    "sea_level_m",
    "water_temperature_c",
)

DELTA_DIRECTION_FIELDS = (
    "wave_direction_deg",
    "swell_direction_deg",
    "wind_direction_deg",
)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite rend des datetimes naïfs ; on les recolle en UTC, ce qui a été écrit."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def signed_angle_delta(new_deg: float, old_deg: float) -> float:
    """Écart de direction dans [−180, 180]. 350° → 10° vaut +20°, pas −340°."""
    return (new_deg - old_deg + 180.0) % 360.0 - 180.0


def latest_run_clause(*, at_or_before: Optional[datetime] = None):
    """Condition « cette ligne appartient au dernier run connu de son créneau ».

    Sous-requête corrélée plutôt que fonction de fenêtre : elle se compose avec
    n'importe quel `select(Forecast)` existant, et elle s'appuie directement sur
    l'index de la contrainte unique `(spot_id, ts, source, run_ts)`.

    `at_or_before` restreint au dernier run **émis avant** un instant donné :
    c'est ce qui distingue « ce qui était annoncé » de « ce qu'on sait
    maintenant », et c'est indispensable au volet `forecast` d'une session.
    """
    other = aliased(Forecast)
    subquery = (
        select(func.max(other.run_ts))
        .where(other.spot_id == Forecast.spot_id)
        .where(other.ts == Forecast.ts)
        .where(other.source == Forecast.source)
    )
    if at_or_before is not None:
        subquery = subquery.where(other.run_ts <= at_or_before)
    return Forecast.run_ts == subquery.scalar_subquery()


def latest_forecasts_select(
    spot_ids: Sequence[int],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    *,
    at_or_before: Optional[datetime] = None,
) -> Select:
    """`SELECT` des prévisions du dernier run, pour les spots et la fenêtre donnés."""
    statement = select(Forecast).where(Forecast.spot_id.in_(list(spot_ids)))
    if start is not None:
        statement = statement.where(Forecast.ts >= start)
    if end is not None:
        statement = statement.where(Forecast.ts <= end)
    return statement.where(latest_run_clause(at_or_before=at_or_before))


async def latest_run_ts(
    db: AsyncSession, spot_id: int, source: str = DEFAULT_SOURCE
) -> Optional[datetime]:
    """Heure d'émission de la prévision la plus récente connue pour ce spot."""
    result = await db.execute(
        select(func.max(Forecast.run_ts))
        .where(Forecast.spot_id == spot_id)
        .where(Forecast.source == source)
    )
    return _as_utc(result.scalar_one_or_none())


# ── Écart entre deux runs ──────────────────────────────────────────────────


def previous_evening_cutoff(
    now: Optional[datetime] = None, timezone: str = "Europe/Paris"
) -> datetime:
    """Hier, `EVENING_HOUR` heure locale, exprimé en UTC.

    Heure locale et pas UTC : « hier soir » est une notion d'utilisateur, et en
    heure d'été le 20 h de Paris est le 18 h UTC. Se tromper de deux heures ici
    ferait comparer au run de l'après-midi.
    """
    now = now or datetime.now(UTC)
    try:
        zone = ZoneInfo(timezone)
    except Exception:  # fuseau inconnu : Paris vaut mieux qu'une exception
        zone = ZoneInfo("Europe/Paris")

    local = now.astimezone(zone)
    evening = local.replace(hour=EVENING_HOUR, minute=0, second=0, microsecond=0)
    # Avant 20 h, « hier soir » est bien hier ; après, c'est encore hier —
    # le soir d'aujourd'hui n'est pas passé du point de vue de la comparaison.
    return (evening - timedelta(days=1)).astimezone(UTC)


@dataclass
class ForecastDelta:
    """Ce qui a changé pour un créneau depuis le run de la veille au soir."""

    spot_id: int
    ts: datetime
    run_ts: Optional[datetime]
    previous_run_ts: Optional[datetime]
    changes: dict[str, float]

    @property
    def available(self) -> bool:
        """Faux tant qu'il n'y a pas deux runs distincts à comparer."""
        return self.previous_run_ts is not None and self.run_ts is not None


async def _row_at(
    db: AsyncSession,
    spot_id: int,
    ts: datetime,
    source: str,
    at_or_before: Optional[datetime] = None,
) -> Optional[Forecast]:
    statement = (
        select(Forecast)
        .where(Forecast.spot_id == spot_id)
        .where(Forecast.ts == ts)
        .where(Forecast.source == source)
        .order_by(Forecast.run_ts.desc())
        .limit(1)
    )
    if at_or_before is not None:
        statement = statement.where(Forecast.run_ts <= at_or_before)
    return (await db.execute(statement)).scalars().first()


async def forecast_delta(
    db: AsyncSession,
    spot: Spot | int,
    ts: datetime,
    *,
    source: str = DEFAULT_SOURCE,
    now: Optional[datetime] = None,
    timezone: str = "Europe/Paris",
) -> ForecastDelta:
    """Écart entre le dernier run et le run de la veille au soir, pour un créneau.

    Renvoie toujours un objet : `available` dit s'il y avait bien deux runs à
    comparer. Un `None` obligerait chaque appelant à retester, alors qu'un delta
    vide se rend tout seul à l'écran — « rien de neuf depuis hier ».

    Le run de référence est le **dernier émis avant hier 20 h locale**, pas le
    premier venu de la veille : c'est ce qu'on avait sous les yeux le soir.
    """
    spot_id = spot if isinstance(spot, int) else spot.id
    ts = ts.astimezone(UTC)
    cutoff = previous_evening_cutoff(now, timezone)

    latest = await _row_at(db, spot_id, ts, source)
    previous = await _row_at(db, spot_id, ts, source, at_or_before=cutoff)

    latest_run = _as_utc(latest.run_ts) if latest else None
    previous_run = _as_utc(previous.run_ts) if previous else None

    # Le run de la veille est aussi le dernier : il n'y a rien à comparer, et
    # surtout pas une ligne avec elle-même.
    if latest is None or previous is None or latest_run == previous_run:
        return ForecastDelta(
            spot_id=spot_id,
            ts=ts,
            run_ts=latest_run,
            previous_run_ts=None if latest_run == previous_run else previous_run,
            changes={},
        )

    changes: dict[str, float] = {}
    for column in DELTA_FIELDS:
        new_value = getattr(latest, column)
        old_value = getattr(previous, column)
        if new_value is None or old_value is None:
            continue
        changes[column] = round(new_value - old_value, 3)

    for column in DELTA_DIRECTION_FIELDS:
        new_value = getattr(latest, column)
        old_value = getattr(previous, column)
        if new_value is None or old_value is None:
            continue
        changes[column] = round(signed_angle_delta(new_value, old_value), 1)

    return ForecastDelta(
        spot_id=spot_id,
        ts=ts,
        run_ts=latest_run,
        previous_run_ts=previous_run,
        changes=changes,
    )
