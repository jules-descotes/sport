from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DailyLogStatus


class DailyLogUpsert(BaseModel):
    """Trois secondes de swipe par jour.

    `day` est une date locale et non un instant : « le 12 septembre » est une
    notion humaine. Le front envoie la date affichée sur le téléphone.
    """

    day: Optional[date] = None
    status: DailyLogStatus
    spot_id: Optional[int] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class DailyLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day: date
    status: str
    spot_id: Optional[int] = None
    reason: Optional[str] = None
    created_at: datetime


class DailyLogToday(BaseModel):
    """Ce que l'écran d'accueil a besoin de savoir : faut-il poser la question ?"""

    day: date
    answered: bool
    entry: Optional[DailyLogRead] = None
