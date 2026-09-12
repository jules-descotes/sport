from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: Optional[str] = None
    height_m: Optional[float] = None
    weight_kg: Optional[float] = None
    level: Optional[str] = None
    disciplines: list[str] = []
    timezone: str = "Europe/Paris"
    # La seule prévision affichée par défaut : celle de ce spot (écran Jour).
    home_spot_id: Optional[int] = None


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    height_m: Optional[float] = Field(default=None, gt=0, lt=3)
    weight_kg: Optional[float] = Field(default=None, gt=0, lt=400)
    level: Optional[str] = None
    disciplines: Optional[list[str]] = None
    timezone: Optional[str] = None
    # Changer de favori change ce qui est ingéré en planifié : le spot est
    # vérifié avant d'être posé, et les niveaux sont recalculés dans la foulée.
    home_spot_id: Optional[int] = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime
    profile: Optional[ProfileRead] = None
