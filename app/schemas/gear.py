from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Discipline, GearType
from app.schemas.types import OptionalUtcDatetime, UtcDatetime


class GearBase(BaseModel):
    """Longueur en mètres, volume en litres.

    Un 6'2 est une unité composite — deux nombres, deux unités, un seul champ —
    et le CLAUDE.md l'interdit en base. Le front affiche des pieds et des
    pouces, comme il affiche des heures locales à partir d'UTC.
    """

    name: str = Field(min_length=1, max_length=40)
    gear_type: GearType = GearType.BOARD
    # 1,50 m à 3,20 m couvre du fish au gun ; en dehors, c'est une faute de
    # frappe et mieux vaut la refuser que la stocker.
    length_m: Optional[float] = Field(default=None, gt=1.0, lt=4.0)
    volume_l: Optional[float] = Field(default=None, gt=0, lt=200)
    discipline: Discipline = Discipline.SURF
    purchased_on: Optional[date] = None


class GearCreate(GearBase):
    pass


class GearUpdate(BaseModel):
    """Tout est optionnel : on corrige un volume sans retaper le reste.

    `is_active` est ici et pas dans `GearCreate` : du matos se crée toujours
    actif, et se range plus tard.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    gear_type: Optional[GearType] = None
    length_m: Optional[float] = Field(default=None, gt=1.0, lt=4.0)
    volume_l: Optional[float] = Field(default=None, gt=0, lt=200)
    discipline: Optional[Discipline] = None
    purchased_on: Optional[date] = None
    is_active: Optional[bool] = None


class GearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    gear_type: str
    length_m: Optional[float] = None
    volume_l: Optional[float] = None
    discipline: str
    purchased_on: Optional[date] = None
    is_active: bool
    created_at: UtcDatetime


class GearWithUsage(GearRead):
    """La même chose, plus l'usure — et l'usure est calculée, jamais saisie.

    `last_used_at` porte la présélection de l'écran de notation : la planche
    proposée est la dernière utilisée, ce qui est juste neuf fois sur dix et se
    corrige d'un tap la dixième.
    """

    session_count: int = 0
    last_used_at: OptionalUtcDatetime = None
