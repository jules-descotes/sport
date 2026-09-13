from __future__ import annotations

from datetime import date, datetime
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
    # Train secondaire — features 16 et 17 du registre. Rendu parce que la
    # ligne repliable de l'écran Surf l'affiche : une houle secondaire de 1 m
    # croisée avec la primaire explique une mer désordonnée que la seule
    # hauteur totale ne raconte pas.
    secondary_swell_height_m: Optional[float] = None
    secondary_swell_direction_deg: Optional[float] = None
    secondary_swell_period_s: Optional[float] = None
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
    # Flux d'énergie de la houle, en kJ/s par mètre de crête (feature 9 du
    # registre, mise à l'échelle physique — cf. `geo.wave_energy_kj`). C'est
    # la ligne « ÉNERGIE » du tableau horaire : elle dit ce que la hauteur
    # seule ne dit pas, à savoir qu'un mètre à 15 s porte trois fois l'énergie
    # d'un mètre à 7 s.
    wave_energy_kj: Optional[float] = None
    # Écart angulaire houle ↔ orientation du spot (feature 10). Nul quand
    # l'orientation de côte est inconnue : on ne devine pas.
    swell_alignment_deg: Optional[float] = None
    score: Optional[float] = None
    score_level: Optional[int] = None
    reasons: list[str] = []
    # Faux la nuit : la grille 5 jours × 8 créneaux éteint la cellule au lieu
    # de la supprimer, sinon la matrice se décale d'une colonne.
    daylight: bool = True


class SunDay(BaseModel):
    """Lever et coucher d'une journée, en UTC.

    Calculés localement (`services/sun.py`), pas demandés à Open-Meteo : c'est
    de l'astronomie, ça tient en trente lignes, et ça ne consomme pas le budget
    d'appels. Le tableau horaire s'en sert pour griser la nuit d'un trait, au
    lieu d'éteindre chaque cellule une par une.
    """

    day: date
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None


class SpotForecastResponse(BaseModel):
    spot: SpotRead
    # `True` quand Open-Meteo a dépassé les cinq secondes : la réponse vient de
    # la base et le complément arrive derrière.
    refreshing: bool = False
    fetched_at: Optional[datetime] = None
    # Heure d'émission du run servi. Distincte de `fetched_at` : elle dit de
    # quelle prévision on parle, là où `fetched_at` ne dit que l'âge du cache.
    run_ts: Optional[datetime] = None
    # Une entrée par journée rendue, dans l'ordre.
    sun: list[SunDay] = []
    points: list[ForecastPoint] = []


class SlotDetail(BaseModel):
    """Le détail d'un créneau — **le seul endroit où les directions sont des
    nombres**.

    Partout ailleurs (tableau horaire, bande de l'écran Jour) une direction est
    une flèche : à bout de bras, au soleil, « 292° » ne se lit pas et « ONO »
    demande une traduction mentale. Une flèche se lit sans réfléchir. Le degré
    reste utile quand on veut comprendre *pourquoi* la note est ce qu'elle est,
    et c'est exactement ce qu'on vient chercher ici.

    Y vit aussi ce qui n'a aucune place dans une grille : l'écart à
    l'orientation du spot, la composante offshore chiffrée, le `run_ts` qui a
    produit ces valeurs et ce qui a changé depuis la veille au soir.
    """

    point: ForecastPoint
    spot: SpotRead

    # Provenances en lettres, pour doubler les degrés sans les remplacer.
    wave_direction_label: Optional[str] = None
    wind_direction_label: Optional[str] = None
    secondary_swell_direction_label: Optional[str] = None
    # Direction dans laquelle le spot regarde la mer — la référence des deux
    # écarts ci-dessus.
    onshore_direction_label: Optional[str] = None

    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None

    # Run qui a produit ces valeurs, et celui de la veille au soir (20 h
    # locale) auquel on le compare.
    run_ts: Optional[datetime] = None
    previous_run_ts: Optional[datetime] = None
    # Écarts signés depuis ce run-là. Les directions sont repliées par le court
    # chemin : 350° → 10° vaut +20°, pas −340°.
    delta: dict[str, float] = {}

    # Coefficient de la pleine mer la plus proche, calculé à Brest — il est
    # national par définition (cf. `services/tide_coefficient`). Nul tant que
    # le spot de référence n'a rien en base : une absence se rend à l'écran,
    # un zéro se lirait comme une morte-eau.
    tide_coefficient: Optional[int] = None
    tide_coefficient_approximate: bool = False
