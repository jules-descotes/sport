from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.types import UtcDatetime

# Les icônes disponibles. Une **petite liste fermée**, et pas une URL ni un
# emoji : les icônes du produit sont en trait de 1,75 px sur une grille de 24,
# et le CLAUDE.md interdit les emoji. Un jeu restreint garantit aussi que
# l'écran Jour reste lisible quelle que soit la combinaison choisie.
HABIT_ICONS = (
    "check",
    "water",
    "sleep",
    "book",
    "leaf",
    "flame",
    "heart",
    "sun",
)

HABIT_KINDS = ("count", "check")
TARGET_PERIODS = ("day", "week")

# `min` — on cherche à en faire au moins tant. `max` — au plus tant (décidé le
# 13/09, retours n° 4). **L'écran ne distingue pas les deux** : compteur,
# objectif, tendance à 7 et 30 jours, dans les deux cas. Le sens sert à écrire
# « sur 3 » ou « max 3 », et rien d'autre — surtout pas une couleur.
TARGET_DIRECTIONS = ("min", "max")


class HabitWrite(BaseModel):
    """Une habitude, telle que Jules la définit.

    L'objectif est **facultatif**, et c'est tout l'esprit : une habitude sans
    objectif est une habitude qu'on observe, pas qu'on se fixe.
    """

    name: str = Field(min_length=1, max_length=60)
    icon: str = "check"
    kind: str = "count"
    unit: Optional[str] = Field(default=None, max_length=20)
    target: Optional[float] = Field(default=None, gt=0, le=1000)
    target_period: str = "day"
    target_direction: str = "min"
    is_active: Optional[bool] = None
    position: Optional[int] = Field(default=None, ge=0, le=50)

    @field_validator("icon")
    @classmethod
    def _icon(cls, value: str) -> str:
        if value not in HABIT_ICONS:
            raise ValueError(f"Icône inconnue : {value}")
        return value

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        if value not in HABIT_KINDS:
            raise ValueError(f"Type inconnu : {value}")
        return value

    @field_validator("target_period")
    @classmethod
    def _period(cls, value: str) -> str:
        if value not in TARGET_PERIODS:
            raise ValueError(f"Période inconnue : {value}")
        return value

    @field_validator("target_direction")
    @classmethod
    def _direction(cls, value: str) -> str:
        if value not in TARGET_DIRECTIONS:
            raise ValueError(f"Sens inconnu : {value}")
        return value


class HabitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon: str
    kind: str
    unit: Optional[str] = None
    target: Optional[float] = None
    target_period: str = "day"
    # `min` ou `max`. Il change le libellé (« sur 3 » / « max 3 ») et **rien
    # d'autre** : ni couleur, ni message, ni série.
    target_direction: str = "min"
    position: int = 0
    is_active: bool = True
    # Le compteur du jour — ce que l'écran Jour affiche sous la pastille.
    today: float = 0.0
    # Le compteur de la semaine, pour les objectifs hebdomadaires.
    week: float = 0.0


class HabitEventWrite(BaseModel):
    """Un tap. `quantity` négatif corrige un tap de trop.

    On annule en ajoutant l'inverse plutôt qu'en supprimant : une correction
    est elle-même une information — le geste a eu lieu, et il a été repris.
    """

    quantity: float = Field(default=1.0, ge=-100, le=100)
    occurred_at: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=120)


class HabitEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    habit_id: int
    occurred_at: UtcDatetime
    quantity: float
    note: Optional[str] = None


# ── Statistiques de profil ─────────────────────────────────────────────────


class SurfStatsRead(BaseModel):
    sessions_30d: int = 0
    hours_30d: float = 0.0
    sessions_season: int = 0
    hours_season: float = 0.0
    # `None` et pas 0 : une moyenne sans session n'existe pas, et un zéro se
    # lirait comme une mauvaise note.
    average_rating: Optional[float] = None
    top_spot: Optional[str] = None
    top_spot_sessions: int = 0
    streak_days: int = 0
    best_rating: Optional[float] = None
    best_spot: Optional[str] = None
    best_day: Optional[date] = None


class NutritionStatsRead(BaseModel):
    logged_days_30d: int = 0
    on_target_days_30d: int = 0
    average_protein_g: Optional[float] = None
    weight_kg: Optional[float] = None
    weight_change_30d: Optional[float] = None


class WeekCountRead(BaseModel):
    week_start: date
    done: int
    planned: int


class TrainingStatsRead(BaseModel):
    weeks: list[WeekCountRead] = []
    done_8w: int = 0
    planned_8w: int = 0
    best_objective: Optional[str] = None
    best_ratio: Optional[float] = None


class HabitTrendRead(BaseModel):
    habit_id: int
    name: str
    icon: str
    unit: Optional[str] = None
    kind: str
    target: Optional[float] = None
    target_period: str = "day"
    target_direction: str = "min"
    total_30d: float = 0.0
    days_with_activity: int = 0
    # Moyennes par jour sur 7 et 30 jours. **C'est la tendance qui suffit**
    # dans les stats de profil (règle F du 13/09, retours n° 4) : une moyenne
    # qui baisse se lit sans qu'on ait besoin de dire si c'est bien.
    average_7d: float = 0.0
    average_30d: float = 0.0
    # La courbe, et rien d'autre : pas de série, pas de taux de réussite. On
    # observe, on n'évalue pas.
    daily: list[float] = []


class ProfileStats(BaseModel):
    """Quatre cartes, des chiffres, aucune morale."""

    day: date
    surf: SurfStatsRead
    nutrition: NutritionStatsRead
    training: TrainingStatsRead
    habits: list[HabitTrendRead] = []
