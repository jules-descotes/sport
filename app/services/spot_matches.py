"""« Parlementia devrait marcher dim. 10 h » — les annonces de l'écran Jour.

Décidé le 13/09. Jour montre la prévision du **favori principal** et rien
d'autre : c'est ce qui garde l'écran lisible. Mais Jules a plusieurs favoris,
et chacun a ses conditions — un spot qui ne marche que trois fois par mois
n'a aucune raison d'occuper l'écran les vingt-sept autres jours, et toutes les
raisons d'être annoncé ces trois jours-là.

D'où cette passe : pour chaque favori, on confronte les trois prochains jours
à **ses** critères (`spot_rules`), et on remonte les fenêtres qui
correspondent, les plus proches en premier, trois au maximum.

Trois décisions valent d'être écrites :

1. **Aucune ingestion ici.** On lit ce que la base a. Les favoris sont au
   niveau `home`, donc ingérés toutes les trois heures de toute façon ; aller
   chercher la prévision de vingt spots à l'ouverture de l'app serait
   exactement ce que le lot 1 ter a retiré.
2. **Un spot sans critères n'est jamais annoncé.** Sans règles, « correspond »
   ne veut rien dire : tous les créneaux correspondraient, et Jour afficherait
   trois annonces permanentes qu'on cesserait de lire en deux jours.
3. **Les créneaux de nuit sont écartés.** Une fenêtre qui correspond à 3 h du
   matin n'est pas une proposition.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SpotTier
from app.models.forecast import Forecast
from app.models.spot import Spot
from app.models.spot_rule import SpotRule
from app.services.forecast_reads import latest_forecasts_select
from app.services.scoring import TideContext, build_conditions, score_conditions
from app.services.spot_rules import (
    MatchWindow,
    SpotRules,
    evaluate,
    group_windows,
    local_hour,
    tide_phase,
)
from app.services.sun import is_daylight

# Trois jours : au-delà, une prévision de houle est une intention, et annoncer
# « samedi prochain » ferait poser un jour de congé sur du sable.
DEFAULT_DAYS = 3

# Trois annonces au maximum. La quatrième ne serait plus lue, et l'écran Jour
# n'a qu'une information en grand — les annonces sont la seconde, pas la
# troisième.
MAX_WINDOWS = 3

# En dessous, la fenêtre est trop courte pour valoir le déplacement : une heure
# isolée à la limite des critères est un faux positif de plus qu'une occasion.
MIN_WINDOW_HOURS = 1.0


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def rules_by_spot(
    db: AsyncSession, user_id: int, spot_ids: Sequence[int]
) -> dict[int, SpotRules]:
    """Les critères de cet utilisateur pour ces spots. Absents = jeu vide."""
    if not spot_ids:
        return {}
    result = await db.execute(
        select(SpotRule)
        .where(SpotRule.user_id == user_id)
        .where(SpotRule.spot_id.in_(list(spot_ids)))
    )
    return {row.spot_id: SpotRules.from_model(row) for row in result.scalars().all()}


async def home_spots(db: AsyncSession, exclude: Sequence[int] = ()) -> list[Spot]:
    """Les spots maison — les favoris, plus le marégraphe qu'on écarte ici."""
    result = await db.execute(
        select(Spot)
        .where(Spot.tier == SpotTier.HOME.value)
        .where(Spot.is_reference.is_(False))
        .order_by(Spot.id)
    )
    excluded = set(exclude)
    return [spot for spot in result.scalars().all() if spot.id not in excluded]


async def upcoming_matches(
    db: AsyncSession,
    user_id: int,
    *,
    days: int = DEFAULT_DAYS,
    timezone: str = "Europe/Paris",
    now: Optional[datetime] = None,
    exclude_spot_ids: Sequence[int] = (),
    limit: int = MAX_WINDOWS,
) -> list[tuple[Spot, MatchWindow]]:
    """Les fenêtres à venir qui correspondent aux critères, les plus proches d'abord.

    `exclude_spot_ids` sert à retirer le favori principal : sa prévision est
    déjà en grand juste au-dessus, et l'annoncer une seconde fois ferait
    doublon. L'écran Jour le mentionne autrement — « et il correspond à tes
    critères » dans le bloc de mer.
    """
    now = now or datetime.now(UTC)
    horizon = now + timedelta(days=days)

    spots = await home_spots(db, exclude_spot_ids)
    if not spots:
        return []

    rules = await rules_by_spot(db, user_id, [spot.id for spot in spots])
    # Un spot sans critères n'est jamais annoncé : sans règles, « correspond »
    # ne veut rien dire.
    spots = [spot for spot in spots if not rules.get(spot.id, SpotRules()).empty]
    if not spots:
        return []

    result = await db.execute(
        latest_forecasts_select(
            [spot.id for spot in spots],
            start=now.replace(minute=0, second=0, microsecond=0),
            end=horizon,
        ).order_by(Forecast.spot_id, Forecast.ts)
    )
    rows_by_spot: dict[int, list] = {}
    for forecast in result.scalars().all():
        rows_by_spot.setdefault(forecast.spot_id, []).append(forecast)

    found: list[tuple[Spot, MatchWindow]] = []
    for spot in spots:
        rows = sorted(rows_by_spot.get(spot.id, []), key=lambda row: _utc(row.ts))
        if not rows:
            continue

        spot_rules = rules[spot.id]
        tide = TideContext.from_levels(
            {_utc(row.ts): row.sea_level_m for row in rows}
        )

        matching: list[tuple[datetime, dict]] = []
        for row in rows:
            ts = _utc(row.ts)
            if not is_daylight(ts, spot.lat, spot.lon):
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
            verdict = evaluate(
                spot_rules,
                wave_height_m=conditions.wave_height_m,
                wave_period_s=conditions.wave_period_s,
                wave_direction_deg=conditions.wave_direction_deg,
                wind_speed_kt=conditions.wind_speed_kt,
                wind_direction_deg=conditions.wind_direction_deg,
                tide_position=conditions.tide_position,
                tide_rising=conditions.rising,
                local_hour=hour,
            )
            if not verdict.matches:
                continue

            score = score_conditions(
                conditions, spot.onshore_dir_deg, spot_rules, hour
            )
            matching.append(
                (
                    ts,
                    {
                        "score": score.value,
                        "wave_height_m": conditions.wave_height_m,
                        "wave_period_s": conditions.wave_period_s,
                        "wave_direction_deg": conditions.wave_direction_deg,
                        "wind_speed_kt": conditions.wind_speed_kt,
                        "wind_direction_deg": conditions.wind_direction_deg,
                        "tide_phase": tide_phase(
                            conditions.tide_position, conditions.rising
                        ),
                    },
                )
            )

        for window in group_windows(spot.id, matching):
            if window.hours >= MIN_WINDOW_HOURS:
                found.append((spot, window))

    # Les plus proches d'abord : ce qui se décide ce soir passe devant ce qui
    # se décide dimanche.
    found.sort(key=lambda pair: pair[1].start)
    return found[:limit]
