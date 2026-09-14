"""Calibration prévision ↔ mesure — la lecture (§7.3).

Un seul endpoint, et il ne décide de rien : il rend ce que trente jours de
paires disent du biais du modèle, par tranche de délai. **Le score ne bouge
pas** (décision du 15/09) : on mesure d'abord, on corrigera avec des mois de
données, pas des jours.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.calibration import CalibrationRead
from app.services.auth_service import get_current_active_user
from app.services.calibration import (
    DEFAULT_WINDOW_DAYS,
    calibration as compute_calibration,
    sentence,
)
from app.services.observations import home_station

router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.get("", response_model=CalibrationRead)
async def read_calibration(
    station: Optional[str] = Query(
        default=None, description="Code de campagne ; défaut : la bouée maison"
    ),
    days: int = Query(default=DEFAULT_WINDOW_DAYS, ge=7, le=365),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CalibrationRead:
    """Biais et erreur absolue moyenne, par tranche de délai.

    Sans `station`, celle du favori principal. Une réponse vide — aucune paire
    — est un état normal tant que la bouée n'a pas tourné quelques jours : la
    carte affiche « pas encore assez de mesures » plutôt qu'un zéro, qui se
    lirait comme un modèle parfait.
    """
    code = station
    if code is None:
        found = await home_station(db)
        code = found[0].code if found else None

    result = await compute_calibration(db, station_code=code, window_days=days)
    payload = result.as_dict()

    # Les phrases sont calculées côté serveur : c'est la même règle de signe
    # que le calcul, et la dupliquer en TypeScript finirait un jour par
    # inverser « sous-estime » et « surestime » sur un seul des deux écrans.
    payload["sentences"] = [
        phrase
        for phrase in (
            sentence(bucket, "la hauteur") for bucket in result.hm0
        )
        if phrase
    ] + [
        phrase
        for phrase in (
            sentence(bucket, "la période") for bucket in result.period
        )
        if phrase
    ]

    return CalibrationRead(**payload)
