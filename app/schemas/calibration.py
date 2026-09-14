"""Schémas de lecture de la calibration."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class BucketRead(BaseModel):
    """Une tranche de délai, et ce qu'elle vaut.

    `pairs` est rendu **même quand il est trop faible** pour donner un chiffre :
    « 4 mesures » est une information, et c'est elle qui s'affiche les premiers
    jours. Un zéro à la place se lirait comme un modèle parfait.
    """

    bucket: str
    pairs: int
    # `observé − prévu`. Positif = le modèle **sous-estime**.
    bias: Optional[float] = None
    mae: Optional[float] = None
    bias_pct: Optional[float] = None
    mean_observed: Optional[float] = None


class CalibrationRead(BaseModel):
    station_id: Optional[str] = None
    window_days: int
    pairs: int
    distance_m: Optional[float] = None
    hm0: list[BucketRead] = []
    period: list[BucketRead] = []
    # Phrases toutes faites, calculées côté serveur pour que le signe du biais
    # ne soit écrit qu'à un seul endroit.
    sentences: list[str] = []
