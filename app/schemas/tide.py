from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.types import UtcDatetime


class TideCoefficientMark(BaseModel):
    """Une pleine mer, et le coefficient qu'elle porte.

    `approximate` est rendu à l'écran par un « ≈ » devant le chiffre. Il est
    vrai dans deux cas : la fenêtre de trente jours qui sert de référence n'est
    pas encore remplie, ou la valeur sort de l'échelle 20–120 du SHOM. Un
    chiffre approximatif annoncé comme exact est pire qu'un chiffre absent.
    """

    ts: UtcDatetime
    value: int
    approximate: bool = False
    reason: Optional[str] = None


class TideCoefficientDay(BaseModel):
    """Les deux pleines mers d'une journée, dans l'ordre.

    Deux, et pas une : leurs coefficients diffèrent d'un ou deux points, et
    « ce matin c'était 95 » ne désigne pas la même marée que « ce soir ».
    """

    day: date
    marks: list[TideCoefficientMark] = []
