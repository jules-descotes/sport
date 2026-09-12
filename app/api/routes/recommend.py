"""Route de recommandation — l'écran d'accueil tient dans cet appel."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.recommend import RecommendResponse, SlotRead, SpotSlots
from app.schemas.spot import SpotRead
from app.services.auth_service import get_current_active_user
from app.services.recommend import Slot, recommend
from app.services.scoring import conditions_line
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
        wave_height_m=conditions.wave_height_m,
        wave_period_s=conditions.wave_period_s,
        wave_direction_deg=conditions.wave_direction_deg,
        wind_speed_kt=conditions.wind_speed_kt,
        wind_gust_kt=conditions.wind_gust_kt,
        wind_direction_deg=conditions.wind_direction_deg,
        sea_level_m=conditions.sea_level_m,
        tide_position=conditions.tide_position,
        tide_rising=conditions.rising,
        water_temperature_c=conditions.water_temperature_c,
        line=conditions_line(conditions),
    )


@router.get("/recommend", response_model=RecommendResponse)
async def get_recommendation(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> RecommendResponse:
    """Verdict du jour, meilleur créneau, et grille complète heures × spots.

    `lat` / `lon` viennent de `navigator.geolocation`. Absents — géoloc refusée
    ou indisponible —, on se rabat sur le domicile du profil : l'écran d'accueil
    ne doit jamais être vide.
    """
    preferences = await get_or_create_preferences(db, current_user.id)

    # Une position fraîche peut ouvrir des spots « potentiels » : on l'enregistre
    # avant de chercher les candidats, sinon le mode trip a un tour de retard.
    if lat is not None and lon is not None:
        await record_position(db, preferences, lat, lon)

    timezone = (
        current_user.profile.timezone if current_user.profile else "Europe/Paris"
    )
    result = await recommend(db, preferences, lat, lon, timezone=timezone)

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
    )
