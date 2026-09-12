from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.spot import SpotRead


class SlotRead(BaseModel):
    """Un créneau noté. Horodatage en UTC : la conversion en heure locale est
    côté front, jamais en base (cf. CLAUDE.md)."""

    ts: datetime
    score: float
    level: int
    verdict: str
    reasons: list[str] = []

    wave_height_m: Optional[float] = None
    wave_period_s: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wind_speed_kt: Optional[float] = None
    wind_gust_kt: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    sea_level_m: Optional[float] = None
    tide_position: Optional[float] = None
    tide_rising: Optional[bool] = None
    water_temperature_c: Optional[float] = None
    line: str = ""


class SpotSlots(BaseModel):
    spot: SpotRead
    distance_km: Optional[float] = None
    best: Optional[SlotRead] = None
    slots: list[SlotRead] = []


class RecommendResponse(BaseModel):
    """Sert l'écran d'accueil *et* le comparateur : un seul aller-retour."""

    generated_at: datetime
    lat: float
    lon: float
    # `device` = géolocalisation acceptée, `home` = repli sur le domicile,
    # `unknown` = ni l'un ni l'autre, l'écran doit le dire.
    position_source: str
    verdict: str
    sentence: str
    headline: Optional[SlotRead] = None
    headline_spot: Optional[SpotRead] = None
    spots: list[SpotSlots] = []
    # Spots dont la prévision se complète en arrière-plan : le front peut
    # relancer la requête dans quelques secondes.
    refreshing: list[int] = []
