from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.spot import RulesPreview, SpotRead
from app.schemas.types import UtcDatetime
from app.services.spot_rules import SECTORS_8, TIDE_PHASES


def _checked(values: list[str], allowed: tuple[str, ...], label: str) -> list[str]:
    """Valide une liste de secteurs ou de phases, et en retire les doublons.

    Refuser explicitement plutôt que d'ignorer : un secteur mal orthographié
    ferait taire une règle en silence, et Jules chercherait longtemps pourquoi
    Parlementia n'est plus jamais annoncé.
    """
    seen: list[str] = []
    for value in values:
        candidate = value.strip().upper() if label == "secteur" else value.strip().lower()
        if candidate not in allowed:
            raise ValueError(
                f"{label} inconnu : {value}. Attendus : {', '.join(allowed)}"
            )
        if candidate not in seen:
            seen.append(candidate)
    return seen


class SpotRuleUpdate(BaseModel):
    """Les critères d'un spot, tels qu'on les saisit sur sa fiche.

    **Tout est optionnel, et vide veut dire « pas de contrainte ».** C'est la
    décision qui structure tout le reste : on ne remplit pas les trous avec des
    seuils inventés, et un spot dont Jules ne sait dire que « pas plus de 2 m »
    est décrit par cette seule ligne.

    L'envoi est **complet** et non partiel : l'écran envoie l'état entier du
    formulaire. Une mise à jour partielle rendrait impossible d'effacer un
    critère — `null` voudrait dire à la fois « ne change pas » et « retire ».
    """

    wave_height_min_m: Optional[float] = Field(default=None, ge=0, le=15)
    wave_height_max_m: Optional[float] = Field(default=None, ge=0, le=15)
    wave_period_min_s: Optional[float] = Field(default=None, ge=0, le=30)
    swell_sectors: list[str] = []
    wind_sectors: list[str] = []
    wind_max_kt: Optional[float] = Field(default=None, ge=0, le=80)
    tide_phases: list[str] = []
    hour_min: Optional[int] = Field(default=None, ge=0, le=23)
    hour_max: Optional[int] = Field(default=None, ge=0, le=23)

    @field_validator("swell_sectors", "wind_sectors")
    @classmethod
    def _sectors(cls, value: list[str]) -> list[str]:
        return _checked(value, SECTORS_8, "secteur")

    @field_validator("tide_phases")
    @classmethod
    def _phases(cls, value: list[str]) -> list[str]:
        return _checked(value, TIDE_PHASES, "phase de marée")


class SpotRuleRead(SpotRuleUpdate):
    model_config = ConfigDict(from_attributes=True)

    spot_id: int
    updated_at: Optional[UtcDatetime] = None
    # L'aperçu immédiat : « sur les 3 prochains jours, ça matcherait N
    # heures ». Nul sur une simple lecture qui ne le demande pas — le calcul
    # relit toute la fenêtre de prévision, et l'écran des critères est le seul
    # qui en a besoin (décidé le 13/09, retours n° 4).
    preview: Optional[RulesPreview] = None


class FavoriteOrder(BaseModel):
    """Le nouvel ordre des favoris, en entier.

    Une liste complète et non un déplacement : réordonner par « monte ce
    spot d'un cran » ferait dépendre le résultat de l'ordre d'arrivée de deux
    requêtes, et il n'y a qu'un doigt pour appuyer.
    """

    spot_ids: list[int] = Field(min_length=0, max_length=20)


class MatchWindowRead(BaseModel):
    """Une fenêtre où un favori correspond à ses critères.

    C'est ce que l'écran Jour annonce sous le bloc de mer : « Parlementia
    devrait marcher — dim. 10 h à 13 h · 1,6 m / 13 s / NO · vent E 6 kt ·
    montante ». Le conditionnel est voulu : ce sont des critères larges
    confrontés à une prévision, pas une promesse.
    """

    spot: SpotRead
    start: UtcDatetime
    end: UtcDatetime
    # Le créneau le mieux noté de la fenêtre — celui qu'on ouvre au tap.
    best_ts: UtcDatetime
    best_score: float
    sentence: str
    details: str
    wave_height_m: Optional[float] = None
    wave_period_s: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wind_speed_kt: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    tide_phase: Optional[str] = None
