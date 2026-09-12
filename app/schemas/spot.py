from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SpotSource, SpotTier, SpotType


class SpotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    lat: float
    lon: float
    country_code: Optional[str] = None
    region: Optional[str] = None
    spot_type: str = SpotType.UNKNOWN.value
    source: str = SpotSource.OSM.value
    # Orientation calculée depuis le trait de côte OSM, jamais saisie.
    coast_bearing_deg: Optional[float] = None
    onshore_dir_deg: Optional[float] = None
    webcam_url: Optional[str] = None
    tier: str = SpotTier.CATALOG.value


class SpotNearby(SpotRead):
    distance_km: float
    is_favorite: bool = False
    is_hidden: bool = False
    # Le favori du profil — celui dont la prévision s'affiche sur Jour.
    is_home: bool = False


class SpotHit(SpotRead):
    """Résultat de recherche de l'écran Mer. Aucune prévision : chercher un spot
    ne doit rien ingérer. La prévision arrive quand on l'ouvre."""

    distance_km: Optional[float] = None
    is_favorite: bool = False
    is_home: bool = False


class SpotCreate(BaseModel):
    """Ajout manuel depuis la carte. La couverture OSM est inégale : là où elle
    est vide, le spot s'ajoute en deux taps et ne sera jamais écrasé par
    l'import mensuel."""

    name: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    spot_type: Optional[str] = None
    country_code: Optional[str] = Field(default=None, max_length=2)
    webcam_url: Optional[str] = None


class SpotUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    spot_type: Optional[str] = None
    webcam_url: Optional[str] = None


class FavoriteRequest(BaseModel):
    favorite: bool = True


class HideRequest(BaseModel):
    hidden: bool = True


class SpotPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    radius_km: float
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    favorite_spot_ids: list[int] = []
    hidden_spot_ids: list[int] = []
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    last_position_at: Optional[datetime] = None


class SpotPreferenceUpdate(BaseModel):
    # 200 km est déjà un trajet de deux heures : au-delà, ce n'est plus une
    # décision du matin.
    radius_km: Optional[float] = Field(default=None, gt=0, le=200)
    home_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    home_lon: Optional[float] = Field(default=None, ge=-180, le=180)


class PositionUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ForecastPoint(BaseModel):
    """Une heure de prévision, en unités de base (m, s, °, kt)."""

    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    wave_height_m: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wave_period_s: Optional[float] = None
    wave_peak_period_s: Optional[float] = None
    swell_height_m: Optional[float] = None
    swell_direction_deg: Optional[float] = None
    swell_period_s: Optional[float] = None
    wind_speed_kt: Optional[float] = None
    wind_gust_kt: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    sea_level_m: Optional[float] = None
    water_temperature_c: Optional[float] = None
    # Position dans la marée du jour : 0 = basse mer, 1 = pleine mer. Nulle
    # quand le marnage est négligeable (Méditerranée, lac) — la marée ne dit
    # alors rien, et mieux vaut se taire qu'afficher un chiffre creux.
    tide_position: Optional[float] = None
    tide_rising: Optional[bool] = None
    tide_range_m: Optional[float] = None
    # Composante offshore signée du vent, en nœuds. Positive = de terre.
    wind_offshore_kt: Optional[float] = None
    score: Optional[float] = None
    score_level: Optional[int] = None
    reasons: list[str] = []
    # Faux la nuit : la grille 5 jours × 8 créneaux éteint la cellule au lieu
    # de la supprimer, sinon la matrice se décale d'une colonne.
    daylight: bool = True


class SpotForecastResponse(BaseModel):
    spot: SpotRead
    # `True` quand Open-Meteo a dépassé les cinq secondes : la réponse vient de
    # la base et le complément arrive derrière.
    refreshing: bool = False
    fetched_at: Optional[datetime] = None
    # Heure d'émission du run servi. Distincte de `fetched_at` : elle dit de
    # quelle prévision on parle, là où `fetched_at` ne dit que l'âge du cache.
    run_ts: Optional[datetime] = None
    points: list[ForecastPoint] = []
