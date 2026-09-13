"""Reco surf — « je vais à l'eau, oui ou non ? ».

Depuis le lot 1 ter, cet appel sert l'écran **Jour**, et il porte par défaut sur
**un seul spot : le favori du profil** (décidé le 12/09 au soir, cf. PROJET.md
§11). Verdict, meilleur créneau, et la journée créneau par créneau.

Sans favori choisi, il se rabat sur les spots du rayon — mais **sans jamais
déclencher d'ingestion** : le rafraîchissement à la demande ne concerne que le
spot qu'on regarde vraiment. C'est la règle « zéro appel tant que personne ne
regarde » prise au mot, spot par spot et non plus rayon par rayon. La grille
multi-spots que renvoie encore ce service alimente le comparateur, qui sort de
la navigation mais reste dans le code.

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
from app.services.forecast_reads import latest_forecasts_select
from app.services.geo import bounding_box, haversine_m
from app.services.scoring import (
    Conditions,
    Score,
    TideContext,
    build_conditions,
    conditions_line,
    score_conditions,
)
from app.services.spot_matches import rules_by_spot as load_spot_rules
from app.services.spot_rules import SpotRules, local_hour
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
    # Le favori du profil, s'il y en a un. Distinct de `headline_spot` : un
    # favori sans prévision n'a pas de créneau vedette, et l'écran doit quand
    # même pouvoir écrire son nom.
    home_spot: Optional[Spot] = None


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
    """Charge les prévisions de la fenêtre, groupées par spot.

    Une heure porte autant de lignes que de passes d'ingestion depuis que
    `run_ts` est dans la clé : on ne garde que le dernier run, sinon la grille
    afficherait la prévision d'avant-hier une cellule sur deux.
    """
    if not spot_ids:
        return {}

    result = await db.execute(
        latest_forecasts_select(spot_ids, start, end).order_by(
            Forecast.spot_id, Forecast.ts
        )
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
    daylight_only: bool = False,
    rules: Optional[SpotRules] = None,
    timezone: str = "Europe/Paris",
) -> list[Slot]:
    """Note tous les créneaux d'un spot, nuit comprise, et dit lesquels sont de jour.

    La nuit était écartée au lot 1. Elle ne l'est plus, parce que la bande des
    huit créneaux de l'écran Jour et la grille de l'écran Mer sont des
    **matrices** : une colonne manquante décale toute la lecture. Les créneaux
    de nuit sont donc rendus, marqués `daylight=False`, et l'écran les éteint.

    Ils restent en revanche exclus du **choix** du meilleur créneau : une note
    de 5 à 3 h du matin n'est pas une proposition.
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
                # Les critères saisis par Jules bornent la note et remplacent
                # l'orientation calculée quand il a listé des secteurs
                # (règle C.4 du 13/09).
                score=score_conditions(
                    conditions,
                    spot.onshore_dir_deg,
                    rules,
                    local_hour(ts, timezone),
                ),
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
    home_spot: Optional[Spot] = None,
) -> Recommendation:
    """Verdict et créneaux du spot favori — ou, à défaut, des spots du rayon."""
    now = now or datetime.now(UTC)

    # Position : celle du téléphone si elle est là, le domicile sinon, le spot
    # favori en dernier recours. Un refus de géolocalisation ne doit jamais
    # donner un écran vide — et quand le favori est choisi, la position ne sert
    # plus qu'à afficher une distance.
    position_source = "device"
    if lat is None or lon is None:
        lat, lon = preferences.home_lat, preferences.home_lon
        position_source = "home"
    if (lat is None or lon is None) and home_spot is not None:
        lat, lon = home_spot.lat, home_spot.lon
        position_source = "spot"
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

    refreshing: list[int] = []
    if home_spot is not None:
        # Une seule prévision par défaut, et c'est la sienne. C'est aussi le
        # seul spot que cet appel a le droit d'ingérer : ouvrir l'app ne doit
        # pas interroger quinze spots qu'on ne regardera pas.
        distance_km = (
            haversine_m(lat, lon, home_spot.lat, home_spot.lon) / 1000.0
        )
        pairs = [(home_spot, distance_km)]
        if refresh:
            refreshing = await ensure_fresh(db, [home_spot])
    else:
        # Pas encore de favori : on montre ce que la base a déjà, sans passer
        # un seul appel. L'écran Jour invite à en choisir un.
        pairs = await candidate_spots(
            db, lat, lon, radius_km, preferences.hidden_spot_ids or []
        )

    spots = [spot for spot, _ in pairs]

    rows_by_spot = await load_forecast_rows(
        db,
        [spot.id for spot in spots],
        now - timedelta(hours=2),
        now + timedelta(days=FORECAST_DAYS),
    )

    # Les critères de Jules pour ces spots, s'il en a posé. Chargés en une
    # requête : une par spot ferait douze allers-retours pour une table de
    # vingt lignes.
    rules_by_spot = await load_spot_rules(
        db, preferences.user_id, [spot.id for spot in spots]
    )

    recommendations: list[SpotRecommendation] = []
    for spot, distance_km in pairs:
        slots = score_spot(
            spot,
            rows_by_spot.get(spot.id, []),
            rules=rules_by_spot.get(spot.id),
            timezone=timezone,
        )
        future = [
            slot
            for slot in slots
            if slot.ts >= now - timedelta(minutes=30) and slot.daylight
        ]
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
            if not slot.daylight or not (window_start <= slot.ts <= window_end):
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
        home_spot=home_spot,
    )
