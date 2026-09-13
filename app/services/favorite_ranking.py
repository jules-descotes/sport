"""Classer les favoris — du meilleur au moins bon, aujourd'hui et demain.

Décidé le 13/09 (retours n° 4), règle B.2. Jour montrait la prévision du favori
principal et, en dessous, trois **annonces** : « Parlementia devrait marcher
dimanche 10 h ». C'était utile et incomplet — une annonce dit qu'un spot
correspond, elle ne dit pas lequel des quatre est le meilleur ce matin, ce qui
est exactement la question qu'on se pose en ouvrant l'app.

La note de journée d'un favori vaut :

    part des heures de jour qui correspondent à SES critères
      ×
    qualité moyenne du score sur ces heures-là

**Le produit, pas la somme**, et c'est tout le calcul. Un spot excellent une
heure par jour et un spot correct toute la journée ne se départagent pas par
addition : le premier demande d'être là à 8 h, le second se décide au réveil.
Le produit dit ça ; une moyenne pondérée le cacherait.

Deux cas méritent leur règle :

- **Un favori sans critères est classé sur le seul score**, et il est
  **signalé**. Sans règles, « correspond » ne veut rien dire — tous ses
  créneaux correspondraient et il finirait toujours premier. On le classe donc
  autrement, et on le dit, pour que le classement reste lisible.
- **Un favori sans prévision n'est pas classé du tout.** Il est rendu, avec
  zéro heure, et l'écran le range en bas. Lui inventer une note serait pire
  que de ne rien afficher : c'est un spot qu'on n'a jamais ingéré, pas un
  mauvais spot.

Aucune ingestion ici. On lit ce que la base a — les favoris sont au niveau
`home` et donc ingérés toutes les trois heures de toute façon (cf. lot 1 ter :
« plus aucun chemin n'ingère un spot qu'on n'a pas regardé »).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast import Forecast
from app.models.spot import Spot
from app.services.forecast_reads import latest_forecasts_select
from app.services.scoring import (
    Thresholds,
    TideContext,
    build_conditions,
    score_conditions,
)
from app.services.spot_matches import rules_by_spot
from app.services.spot_rules import SpotRules, evaluate, local_hour
from app.services.sun import is_daylight
from app.services.thresholds import load as load_thresholds

# Aujourd'hui et demain. Au-delà, une prévision de houle est une intention, et
# classer des spots sur samedi ferait poser un jour de congé sur du sable.
DEFAULT_DAYS = 2


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass
class DayRanking:
    """Ce qu'un favori vaut pour une journée donnée."""

    day: date
    # Heures de jour disponibles dans la prévision, et heures qui correspondent.
    daylight_hours: int = 0
    matching_hours: int = 0
    # Moyenne du score sur les heures retenues — celles qui correspondent, ou
    # toutes les heures de jour pour un spot sans critères.
    average_score: float = 0.0
    # `part × qualité`. C'est lui qui classe.
    day_score: float = 0.0
    best_ts: Optional[datetime] = None
    best_score: Optional[float] = None
    # Début et fin de la meilleure plage continue qui corresponde.
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None

    @property
    def match_ratio(self) -> float:
        if not self.daylight_hours:
            return 0.0
        return self.matching_hours / self.daylight_hours


@dataclass
class SpotRanking:
    spot: Spot
    has_rules: bool
    is_home: bool
    days: list[DayRanking] = field(default_factory=list)

    @property
    def best_day_score(self) -> float:
        return max((day.day_score for day in self.days), default=0.0)

    @property
    def has_forecast(self) -> bool:
        return any(day.daylight_hours for day in self.days)


def _local_days(now: datetime, zone: ZoneInfo, days: int) -> list[date]:
    today = now.astimezone(zone).date()
    return [today + timedelta(days=offset) for offset in range(days)]


def _rank_day(
    spot: Spot,
    rules: SpotRules,
    rows: Sequence[Forecast],
    tide: TideContext,
    day: date,
    zone: ZoneInfo,
    timezone: str,
    thresholds: Thresholds,
    now: datetime,
) -> DayRanking:
    ranking = DayRanking(day=day)

    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = start + timedelta(days=1)

    scored: list[tuple[datetime, float, bool]] = []
    for row in rows:
        ts = _utc(row.ts)
        if not (start <= ts < end):
            continue
        if not is_daylight(ts, spot.lat, spot.lon):
            continue
        # Une heure déjà passée ne se propose pas. Aujourd'hui, le classement
        # porte donc sur ce qui reste de la journée — c'est ce qu'on décide.
        if ts < now.replace(minute=0, second=0, microsecond=0):
            continue

        conditions = build_conditions(
            ts,
            {
                "wave_height_m": row.wave_height_m,
                "wave_direction_deg": row.wave_direction_deg,
                "wave_period_s": row.wave_period_s,
                "wind_speed_kt": row.wind_speed_kt,
                "wind_gust_kt": row.wind_gust_kt,
                "wind_direction_deg": row.wind_direction_deg,
                "sea_level_m": row.sea_level_m,
                "water_temperature_c": row.water_temperature_c,
            },
            tide,
        )
        hour = local_hour(ts, timezone)
        score = score_conditions(
            conditions, spot.onshore_dir_deg, rules, hour, thresholds
        )

        matches = True
        if not rules.empty:
            matches = evaluate(
                rules,
                wave_height_m=conditions.wave_height_m,
                wave_period_s=conditions.wave_period_s,
                wave_direction_deg=conditions.wave_direction_deg,
                wind_speed_kt=conditions.wind_speed_kt,
                wind_direction_deg=conditions.wind_direction_deg,
                tide_position=conditions.tide_position,
                tide_rising=conditions.rising,
                local_hour=hour,
            ).matches

        scored.append((ts, score.value, matches))

    ranking.daylight_hours = len(scored)
    if not scored:
        return ranking

    kept = [entry for entry in scored if entry[2]]
    ranking.matching_hours = len(kept)

    # Sans critères, on note sur toutes les heures de jour : « correspond » ne
    # veut rien dire, mais la qualité, si.
    basis = kept if kept else ([] if not rules.empty else scored)
    if not basis:
        return ranking

    ranking.average_score = round(
        sum(entry[1] for entry in basis) / len(basis), 2
    )

    best = max(basis, key=lambda entry: entry[1])
    ranking.best_ts, ranking.best_score = best[0], round(best[1], 2)

    # La note de journée. Pour un spot sans critères, la part vaut 1 : on ne
    # peut pas la calculer, et la mettre à zéro le ferait disparaître du
    # classement alors qu'on vient justement de le mettre en favori.
    ratio = ranking.match_ratio if not rules.empty else 1.0
    ranking.day_score = round(ratio * ranking.average_score, 2)

    if kept:
        ranking.window_start, ranking.window_end = _best_window(kept)

    return ranking


def _best_window(
    kept: Sequence[tuple[datetime, float, bool]],
) -> tuple[datetime, datetime]:
    """La plage continue la mieux notée parmi les heures qui correspondent.

    « Continue » à l'heure près : deux heures qui correspondent séparées par
    une qui ne correspond pas ne font pas une fenêtre de trois heures, elles en
    font deux d'une heure — et c'est la différence entre y aller et regretter.
    """
    ordered = sorted(kept, key=lambda entry: entry[0])
    runs: list[list[tuple[datetime, float, bool]]] = [[ordered[0]]]
    for entry in ordered[1:]:
        if entry[0] - runs[-1][-1][0] <= timedelta(hours=1):
            runs[-1].append(entry)
        else:
            runs.append([entry])

    best_run = max(
        runs, key=lambda run: (sum(item[1] for item in run) / len(run), len(run))
    )
    return best_run[0][0], best_run[-1][0] + timedelta(hours=1)


async def rank_favorites(
    db: AsyncSession,
    user_id: int,
    favorites: Sequence[Spot],
    *,
    home_spot_id: Optional[int] = None,
    days: int = DEFAULT_DAYS,
    timezone: str = "Europe/Paris",
    now: Optional[datetime] = None,
) -> list[SpotRanking]:
    """Les favoris, du meilleur au moins bon. Aucune ingestion.

    L'ordre est celui de la meilleure note de journée sur la fenêtre demandée.
    À égalité, le favori principal passe devant : c'est celui qu'on regarde
    tous les matins, et le départager au hasard ferait changer l'ordre d'un
    rafraîchissement à l'autre.
    """
    if not favorites:
        return []

    now = now or datetime.now(UTC)
    try:
        zone = ZoneInfo(timezone)
    except Exception:  # noqa: BLE001 — fuseau invalide en base
        zone = ZoneInfo("Europe/Paris")
        timezone = "Europe/Paris"

    wanted = _local_days(now, zone, days)
    horizon = datetime.combine(
        wanted[-1] + timedelta(days=1), time.min, tzinfo=zone
    ).astimezone(UTC)

    rules = await rules_by_spot(db, user_id, [spot.id for spot in favorites])
    thresholds = await load_thresholds(db, user_id)

    result = await db.execute(
        latest_forecasts_select(
            [spot.id for spot in favorites],
            start=now.replace(minute=0, second=0, microsecond=0),
            end=horizon,
        ).order_by(Forecast.spot_id, Forecast.ts)
    )
    rows_by_spot: dict[int, list[Forecast]] = {}
    for forecast in result.scalars().all():
        rows_by_spot.setdefault(forecast.spot_id, []).append(forecast)

    rankings: list[SpotRanking] = []
    for spot in favorites:
        spot_rules = rules.get(spot.id, SpotRules())
        rows = rows_by_spot.get(spot.id, [])
        tide = TideContext.from_levels(
            {_utc(row.ts): row.sea_level_m for row in rows}
        )
        rankings.append(
            SpotRanking(
                spot=spot,
                has_rules=not spot_rules.empty,
                is_home=spot.id == home_spot_id,
                days=[
                    _rank_day(
                        spot,
                        spot_rules,
                        rows,
                        tide,
                        day,
                        zone,
                        timezone,
                        thresholds,
                        now,
                    )
                    for day in wanted
                ],
            )
        )

    # Sans prévision, un spot descend en bas — et il n'est pas noté pour
    # autant : c'est un spot qu'on n'a jamais ingéré, pas un mauvais spot.
    rankings.sort(
        key=lambda entry: (
            entry.has_forecast,
            entry.best_day_score,
            entry.is_home,
        ),
        reverse=True,
    )
    return rankings


async def matching_hours_preview(
    db: AsyncSession,
    user_id: int,
    spot: Spot,
    rules: SpotRules,
    *,
    days: int = 3,
    timezone: str = "Europe/Paris",
    now: Optional[datetime] = None,
) -> tuple[int, int]:
    """`(heures qui correspondent, heures de jour disponibles)` sur N jours.

    C'est l'aperçu immédiat de la fiche de critères (règle B.3 du 13/09) :
    « sur les 3 prochains jours, ça matcherait 7 heures ». Sans lui, on règle
    des seuils à l'aveugle et on découvre trois jours plus tard qu'on a écrit
    des critères que la côte ne remplit jamais.
    """
    now = now or datetime.now(UTC)
    try:
        zone = ZoneInfo(timezone)
    except Exception:  # noqa: BLE001
        zone = ZoneInfo("Europe/Paris")
        timezone = "Europe/Paris"

    horizon = now + timedelta(days=days)
    result = await db.execute(
        latest_forecasts_select(
            [spot.id],
            start=now.replace(minute=0, second=0, microsecond=0),
            end=horizon,
        ).order_by(Forecast.ts)
    )
    rows = list(result.scalars().all())
    if not rows:
        return 0, 0

    tide = TideContext.from_levels(
        {_utc(row.ts): row.sea_level_m for row in rows}
    )

    daylight = 0
    matching = 0
    for row in rows:
        ts = _utc(row.ts)
        if not is_daylight(ts, spot.lat, spot.lon):
            continue
        daylight += 1

        conditions = build_conditions(
            ts,
            {
                "wave_height_m": row.wave_height_m,
                "wave_direction_deg": row.wave_direction_deg,
                "wave_period_s": row.wave_period_s,
                "wind_speed_kt": row.wind_speed_kt,
                "wind_gust_kt": row.wind_gust_kt,
                "wind_direction_deg": row.wind_direction_deg,
                "sea_level_m": row.sea_level_m,
                "water_temperature_c": row.water_temperature_c,
            },
            tide,
        )
        if rules.empty:
            continue
        if evaluate(
            rules,
            wave_height_m=conditions.wave_height_m,
            wave_period_s=conditions.wave_period_s,
            wave_direction_deg=conditions.wave_direction_deg,
            wind_speed_kt=conditions.wind_speed_kt,
            wind_direction_deg=conditions.wind_direction_deg,
            tide_position=conditions.tide_position,
            tide_rising=conditions.rising,
            local_hour=local_hour(ts, timezone),
        ).matches:
            matching += 1

    return matching, daylight
