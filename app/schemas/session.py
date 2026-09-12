from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Discipline


class SurfSessionCreate(BaseModel):
    """Squelette du lot 1 : l'endpoint existe et fige le snapshot, le formulaire
    de saisie arrive au lot 2 avec le chemin rapide et la file hors ligne.

    `started_at` peut être dans le passé : une session rétroactive déclenche le
    même backfill d'archive qu'une session enregistrée sur le parking.
    """

    spot_id: int
    started_at: datetime
    duration_min: Optional[int] = Field(default=None, gt=0, le=600)
    discipline: Discipline = Discipline.SURF

    # Deux notes, jamais une seule (cf. CLAUDE.md, règle 6).
    rating_conditions: Optional[int] = Field(default=None, ge=1, le=5)
    rating_personal: Optional[int] = Field(default=None, ge=1, le=5)

    wave_count: Optional[int] = Field(default=None, ge=0, le=500)
    crowd: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=2000)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)


class SurfSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    spot_id: int
    started_at: datetime
    duration_min: Optional[int] = None
    discipline: str
    rating_conditions: Optional[int] = None
    rating_personal: Optional[int] = None
    wave_count: Optional[int] = None
    crowd: Optional[int] = None
    notes: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    # Figé à l'enregistrement, en fenêtre T−2 h / T−1 h / T0, deux volets.
    conditions_snapshot: Optional[dict[str, Any]] = None
    created_at: datetime
