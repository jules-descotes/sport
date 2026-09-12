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
    # Faux la nuit. Le créneau est quand même rendu — la bande de l'écran Jour
    # est une matrice, une colonne manquante décale toute la lecture — mais il
    # est éteint à l'écran et jamais proposé comme meilleur créneau.
    daylight: bool = True

    wave_height_m: Optional[float] = None
    wave_period_s: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wind_speed_kt: Optional[float] = None
    wind_gust_kt: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    sea_level_m: Optional[float] = None
    tide_position: Optional[float] = None
    tide_rising: Optional[bool] = None
    # Marnage du jour, en mètres (feature 8 du registre).
    tide_range_m: Optional[float] = None
    water_temperature_c: Optional[float] = None
    # Composante offshore signée du vent, en nœuds. Positive = de terre.
    # Nulle quand l'orientation de la côte est inconnue : on ne devine pas.
    wind_offshore_kt: Optional[float] = None
    line: str = ""


class SpotSlots(BaseModel):
    spot: SpotRead
    distance_km: Optional[float] = None
    best: Optional[SlotRead] = None
    slots: list[SlotRead] = []


class RecommendResponse(BaseModel):
    """Sert l'écran Jour : le spot favori, son verdict et sa journée."""

    generated_at: datetime
    lat: float
    lon: float
    # `device` = géolocalisation acceptée, `home` = repli sur le domicile,
    # `spot` = repli sur le spot favori, `unknown` = rien de tout ça, et
    # l'écran doit le dire.
    position_source: str
    verdict: str
    sentence: str
    headline: Optional[SlotRead] = None
    headline_spot: Optional[SpotRead] = None
    # Le favori du profil. `None` = aucun favori choisi : l'écran Jour invite à
    # en choisir un plutôt que d'afficher la mer de quelqu'un d'autre.
    home_spot: Optional[SpotRead] = None
    # Heure d'émission de la prévision servie. C'est le bénéfice visible de
    # `run_ts` : l'écran peut dire « prévision de 6 h » au lieu de laisser
    # croire que la mer vient d'être regardée.
    run_ts: Optional[datetime] = None
    spots: list[SpotSlots] = []
    # Spots dont la prévision se complète en arrière-plan : le front peut
    # relancer la requête dans quelques secondes.
    refreshing: list[int] = []
