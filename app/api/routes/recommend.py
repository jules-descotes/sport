"""Route de recommandation — l'écran d'accueil tient dans cet appel."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.spot import Spot
from app.models.user import User
from app.schemas.recommend import RecommendResponse, SlotRead, SpotSlots
from app.schemas.spot import SpotRead
from app.schemas.spot_rule import MatchWindowRead
from app.services.auth_service import get_current_active_user
from app.services.forecast_reads import latest_run_ts
from app.services.recommend import Slot, recommend
from app.services.scoring import conditions_line
from app.services.spot_matches import upcoming_matches
from app.services.spot_rules import window_details, window_sentence
from app.services.spot_tiers import get_or_create_preferences, record_position

router = APIRouter(tags=["recommend"])


def _slot_read(slot: Slot) -> SlotRead:
    conditions = slot.conditions
    return SlotRead(
        ts=slot.ts,
        score=slot.score.value,
        level=slot.score.level,
        verdict=slot.score.verdict,
        reasons=slot.score.reasons,
        daylight=slot.daylight,
        wave_height_m=conditions.wave_height_m,
        wave_period_s=conditions.wave_period_s,
        wave_direction_deg=conditions.wave_direction_deg,
        wind_speed_kt=conditions.wind_speed_kt,
        wind_gust_kt=conditions.wind_gust_kt,
        wind_direction_deg=conditions.wind_direction_deg,
        sea_level_m=conditions.sea_level_m,
        tide_position=conditions.tide_position,
        tide_rising=conditions.rising,
        tide_range_m=conditions.tide_range_m,
        water_temperature_c=conditions.water_temperature_c,
        # Composante offshore signée (feature 11 du registre) : positive, le
        # vent vient de la terre. C'est elle qui permet d'écrire « de terre » ou
        # « de mer » à l'écran sans refaire le calcul côté front, qui ne connaît
        # pas l'orientation de la côte.
        wind_offshore_kt=slot.score.components.get("offshore_kt"),
        line=conditions_line(conditions),
    )


@router.get("/recommend", response_model=RecommendResponse)
async def get_recommendation(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecommendResponse:
    """L'écran Jour : le verdict du spot favori et sa journée créneau par créneau.

    `lat` / `lon` viennent de `navigator.geolocation`, et ne servent plus qu'à
    afficher une distance et à tenir la position courante à jour. Le spot, lui,
    vient du profil.

    **C'est le seul spot que cet appel ingère.** Ouvrir l'app n'interroge pas le
    rayon : tout autre spot n'est récupéré que depuis l'écran Mer, quand on le
    regarde.
    """
    preferences = await get_or_create_preferences(db, current_user.id)

    # Une position fraîche étiquette les spots « potentiels » autour de nous :
    # elle ne déclenche plus aucun appel, elle prépare la recherche « autour de
    # moi » de l'écran Mer.
    if lat is not None and lon is not None:
        await record_position(db, preferences, lat, lon)

    profile = current_user.profile
    timezone = profile.timezone if profile else "Europe/Paris"

    home_spot = None
    if profile is not None and profile.home_spot_id is not None:
        home_spot = (
            await db.execute(select(Spot).where(Spot.id == profile.home_spot_id))
        ).scalar_one_or_none()

    result = await recommend(
        db, preferences, lat, lon, timezone=timezone, home_spot=home_spot
    )

    # Les autres favoris qui devraient marcher, d'après les critères saisis.
    # Le favori principal est exclu : sa prévision est déjà en grand au-dessus,
    # et l'annoncer une seconde fois ferait doublon — le bloc de mer le dit
    # autrement, par `home_matches`.
    now = result.generated_at
    matches = await upcoming_matches(
        db,
        current_user.id,
        timezone=timezone,
        now=now,
        exclude_spot_ids=[] if home_spot is None else [home_spot.id],
    )

    # Le favori principal correspond-il à ses propres critères, sur le créneau
    # qu'on affiche en grand ?
    home_matches = False
    if home_spot is not None and result.headline is not None:
        home_matches = bool(
            result.headline.score.components.get("rule_match")
        )

    return RecommendResponse(
        generated_at=result.generated_at,
        lat=result.lat,
        lon=result.lon,
        position_source=result.position_source,
        verdict=result.verdict,
        sentence=result.sentence,
        headline=_slot_read(result.headline) if result.headline else None,
        headline_spot=(
            SpotRead.model_validate(result.headline_spot)
            if result.headline_spot
            else None
        ),
        home_spot=(
            SpotRead.model_validate(result.home_spot) if result.home_spot else None
        ),
        run_ts=(
            await latest_run_ts(db, home_spot.id) if home_spot is not None else None
        ),
        spots=[
            SpotSlots(
                spot=SpotRead.model_validate(item.spot),
                distance_km=(
                    round(item.distance_km, 2) if item.distance_km is not None else None
                ),
                best=_slot_read(item.best) if item.best else None,
                slots=[_slot_read(slot) for slot in item.slots],
            )
            for item in result.spots
        ],
        refreshing=result.refreshing,
        matches=[
            MatchWindowRead(
                spot=SpotRead.model_validate(spot),
                start=window.start,
                end=window.end,
                best_ts=window.best_ts,
                best_score=window.best_score,
                sentence=window_sentence(window, spot.name, now, timezone),
                details=window_details(window),
                wave_height_m=window.wave_height_m,
                wave_period_s=window.wave_period_s,
                wave_direction_deg=window.wave_direction_deg,
                wind_speed_kt=window.wind_speed_kt,
                wind_direction_deg=window.wind_direction_deg,
                tide_phase=window.tide_phase,
            )
            for spot, window in matches
        ],
        home_matches=home_matches,
    )
