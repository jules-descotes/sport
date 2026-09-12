"""Reco surf — « je vais à l'eau, oui ou non, et où ? ».

Un seul appel sert l'écran d'accueil *et* le comparateur : le verdict, le
meilleur créneau, et la grille heures × spots. Deux requêtes pour deux écrans
qui s'ouvrent l'un après l'autre coûteraient une seconde de plus sur le parking
de la plage, pour la même donnée.

Au lot 1 la note vient des règles génériques de `scoring.py`. Au lot 3 elle
viendra d'une régression, puis du plus proche voisin — la forme de la réponse
ne changera pas, seule la fonction de notation sera remplacée.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SpotTier
from app.models.forecast import Forecast
from app.models.spot import Spot, SpotPreference
from app.services.forecast_ingest import ensure_fresh
from app.services.geo import bounding_box, haversine_m
from app.services.scoring import (
    Conditions,
    Score,
    TideContext,
    build_conditions,
    conditions_line,
    score_conditions,
)
from app.services.sun import is_daylight, next_daylight_window

# Au-delà, on ne prend plus la voiture pour aller voir.
DEFAULT_RADIUS_KM = 40.0
# Le catalogue est mondial ; l'écran d'accueil ne l'est pas.
MAX_SPOTS = 12
FORECAST_DAYS = 5

_JOURS = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)


@dataclass
class Slot:
    """Un créneau horaire noté, pour un spot."""

    ts: datetime
    conditions: Conditions
    score: Score
    daylight: bool


@dataclass
class SpotRecommendation:
    spot: Spot
    distance_km: Optional[float]
    slots: list[Slot]
    best: Optional[Slot]


@dataclass
class Recommendation:
    generated_at: datetime
    lat: float
    lon: float
    position_source: str
    spots: list[SpotRecommendation]
    headline: Optional[Slot]
    headline_spot: Optional[Spot]
    verdict: str
    sentence: str
    refreshing: list[int]


async def candidate_spots(
    db: AsyncSession,
    lat: float,
    lon: float,
    radius_km: float,
    hidden_ids: Sequence[int] = (),
    limit: int = MAX_SPOTS,
) -> list[tuple[Spot, float]]:
    """Spots `home` et `potential` autour de la position, les plus proches d'abord.

    Les spots `catalog` sont volontairement exclus : ils n'ont pas de prévision
    et n'en auront pas, les interroger à la volée reviendrait à ingérer le monde
    entier à chaque ouverture de l'app.
    """
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)

    result = await db.execute(
        select(Spot)
        .where(Spot.tier.in_([SpotTier.HOME.value, SpotTier.POTENTIAL.value]))
        .where(Spot.lat.between(min_lat, max_lat))
        .where(Spot.lon.between(min_lon, max_lon))
    )

    hidden = set(hidden_ids)
    scored: list[tuple[Spot, float]] = []
    for spot in result.scalars().all():
        if spot.id in hidden:
            continue
        distance_km = haversine_m(lat, lon, spot.lat, spot.lon) / 1000.0
        if distance_km <= radius_km:
            scored.append((spot, distance_km))

    # Les favoris passent devant, à distance comparable : ce sont les seuls dont
    # la prévision est garantie fraîche.
    scored.sort(
        key=lambda pair: (pair[0].tier != SpotTier.HOME.value, pair[1])
    )
    return scored[:limit]


async def load_forecast_rows(
    db: AsyncSession, spot_ids: Sequence[int], start: datetime, end: datetime
) -> dict[int, list[tuple[datetime, dict[str, Optional[float]]]]]:
    """Charge les prévisions de la fenêtre, groupées par spot."""
    if not spot_ids:
        return {}

    result = await db.execute(
        select(Forecast)
        .where(Forecast.spot_id.in_(list(spot_ids)))
        .where(Forecast.ts >= start)
        .where(Forecast.ts <= end)
        .order_by(Forecast.spot_id, Forecast.ts)
    )

    rows: dict[int, list[tuple[datetime, dict[str, Optional[float]]]]] = {}
    for forecast in result.scalars().all():
        ts = forecast.ts if forecast.ts.tzinfo else forecast.ts.replace(tzinfo=UTC)
        rows.setdefault(forecast.spot_id, []).append(
            (
                ts,
                {
                    "wave_height_m": forecast.wave_height_m,
                    "wave_direction_deg": forecast.wave_direction_deg,
                    "wave_period_s": forecast.wave_period_s,
                    "wave_peak_period_s": forecast.wave_peak_period_s,
                    "swell_height_m": forecast.swell_height_m,
                    "swell_direction_deg": forecast.swell_direction_deg,
                    "swell_period_s": forecast.swell_period_s,
                    "wind_speed_kt": forecast.wind_speed_kt,
                    "wind_gust_kt": forecast.wind_gust_kt,
                    "wind_direction_deg": forecast.wind_direction_deg,
                    "sea_level_m": forecast.sea_level_m,
                    "water_temperature_c": forecast.water_temperature_c,
                },
            )
        )
    return rows


def score_spot(
    spot: Spot,
    rows: Sequence[tuple[datetime, dict[str, Optional[float]]]],
    daylight_only: bool = True,
) -> list[Slot]:
    """Note tous les créneaux d'un spot.

    Les créneaux de nuit sont notés puis écartés : on surfe rarement à 3 h du
    matin, et une note de 5 à cette heure-là dans le comparateur ferait perdre
    trois secondes de lecture pour rien.
    """
    tide = TideContext.from_levels({ts: values.get("sea_level_m") for ts, values in rows})

    slots: list[Slot] = []
    for ts, values in rows:
        daylight = is_daylight(ts, spot.lat, spot.lon)
        if daylight_only and not daylight:
            continue
        conditions = build_conditions(ts, values, tide)
        slots.append(
            Slot(
                ts=ts,
                conditions=conditions,
                score=score_conditions(conditions, spot.onshore_dir_deg),
                daylight=daylight,
            )
        )
    return slots


def _day_label(ts_local: datetime, now_local: datetime) -> str:
    delta_days = (ts_local.date() - now_local.date()).days
    if delta_days == 0:
        return "Aujourd'hui"
    if delta_days == 1:
        return "Demain"
    return _JOURS[ts_local.weekday()].capitalize()


def _hour_label(ts_local: datetime) -> str:
    if ts_local.minute:
        return f"{ts_local.hour} h {ts_local.minute:02d}"
    return f"{ts_local.hour} h"


def build_sentence(
    spot: Optional[Spot],
    slot: Optional[Slot],
    now: datetime,
    timezone: str = "Europe/Paris",
) -> str:
    """« Demain 8 h — Les Cavaliers, 4,2/5 · houle 1,4 m / 12 s / NO, vent E 8 kt »."""
    if spot is None or slot is None:
        return "Pas de prévision disponible pour les spots autour de toi."

    try:
        zone = ZoneInfo(timezone)
    except Exception:  # fuseau inconnu : l'heure de Paris vaut mieux qu'une erreur
        zone = ZoneInfo("Europe/Paris")

    ts_local = slot.ts.astimezone(zone)
    now_local = now.astimezone(zone)
    note = f"{slot.score.value:.1f}".replace(".", ",")

    head = (
        f"{_day_label(ts_local, now_local)} {_hour_label(ts_local)} — "
        f"{spot.name}, {note}/5"
    )
    line = conditions_line(slot.conditions)
    return f"{head} · {line}" if line else head


async def recommend(
    db: AsyncSession,
    preferences: SpotPreference,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    timezone: str = "Europe/Paris",
    now: Optional[datetime] = None,
    refresh: bool = True,
) -> Recommendation:
    """Verdict, meilleur créneau et grille complète, en un appel."""
    now = now or datetime.now(UTC)

    # Position : celle du téléphone si elle est là, le domicile sinon. Un refus
    # de géolocalisation ne doit jamais donner un écran vide.
    position_source = "device"
    if lat is None or lon is None:
        lat, lon = preferences.home_lat, preferences.home_lon
        position_source = "home"
    if lat is None or lon is None:
        return Recommendation(
            generated_at=now,
            lat=0.0,
            lon=0.0,
            position_source="unknown",
            spots=[],
            headline=None,
            headline_spot=None,
            verdict="NON",
            sentence="Choisis un domicile dans le profil, ou autorise la géolocalisation.",
            refreshing=[],
        )

    radius_km = preferences.radius_km or DEFAULT_RADIUS_KM
    pairs = await candidate_spots(
        db, lat, lon, radius_km, preferences.hidden_spot_ids or []
    )
    spots = [spot for spot, _ in pairs]

    refreshing: list[int] = []
    if refresh and spots:
        refreshing = await ensure_fresh(db, spots)

    rows_by_spot = await load_forecast_rows(
        db,
        [spot.id for spot in spots],
        now - timedelta(hours=2),
        now + timedelta(days=FORECAST_DAYS),
    )

    recommendations: list[SpotRecommendation] = []
    for spot, distance_km in pairs:
        slots = score_spot(spot, rows_by_spot.get(spot.id, []))
        future = [slot for slot in slots if slot.ts >= now - timedelta(minutes=30)]
        best = max(future, key=lambda slot: slot.score.value, default=None)
        recommendations.append(
            SpotRecommendation(
                spot=spot, distance_km=distance_km, slots=slots, best=best
            )
        )

    # Le verdict ne porte que sur la prochaine fenêtre de jour : « j'y vais ou
    # pas » ne se pose pas pour après-demain.
    window_start, window_end = next_daylight_window(now, lat, lon)
    headline: Optional[Slot] = None
    headline_spot: Optional[Spot] = None
    for recommendation in recommendations:
        for slot in recommendation.slots:
            if not (window_start <= slot.ts <= window_end):
                continue
            if headline is None or slot.score.value > headline.score.value:
                headline, headline_spot = slot, recommendation.spot

    # Rien dans la fenêtre du jour (prévision absente, nuit tombée) : on se
    # rabat sur le meilleur créneau à venir, tous jours confondus.
    if headline is None:
        best_overall = max(
            (r for r in recommendations if r.best is not None),
            key=lambda r: r.best.score.value,
            default=None,
        )
        if best_overall is not None:
            headline, headline_spot = best_overall.best, best_overall.spot

    recommendations.sort(
        key=lambda r: r.best.score.value if r.best else 0.0, reverse=True
    )

    return Recommendation(
        generated_at=now,
        lat=lat,
        lon=lon,
        position_source=position_source,
        spots=recommendations,
        headline=headline,
        headline_spot=headline_spot,
        verdict=headline.score.verdict if headline else "NON",
        sentence=build_sentence(headline_spot, headline, now, timezone),
        refreshing=refreshing,
    )
