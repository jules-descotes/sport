"""Coefficients de marée.

Une seule route, et elle ne prend pas de spot : **le coefficient est national**.
Le SHOM le calcule au port de référence de Brest, et il vaut de Dunkerque à
Hendaye. Le paramétrer par spot laisserait croire le contraire.

Le calcul, la constante de Brest et la règle du « ≈ » vivent dans
`services/tide_coefficient` ; ici il n'y a que la fenêtre demandée et la mise
en forme.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.tide import TideCoefficientDay, TideCoefficientMark
from app.services.auth_service import get_current_active_user
from app.services.tide_coefficient import coefficients

router = APIRouter(prefix="/tides", tags=["tides"])


@router.get("/coefficients", response_model=list[TideCoefficientDay])
async def read_coefficients(
    start: Optional[date] = Query(
        default=None, description="Premier jour, en UTC. Défaut : aujourd'hui."
    ),
    days: int = Query(default=5, ge=1, le=31),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[TideCoefficientDay]:
    """Les coefficients des pleines mers, jour par jour.

    Rend une liste **vide** tant que le marégraphe de Brest n'a rien en base :
    les premières heures après un déploiement, ou si Open-Meteo est
    indisponible. L'écran n'affiche alors pas de coefficient, ce qui est la
    bonne réponse — mieux vaut pas de chiffre qu'un chiffre inventé.

    La fenêtre accepte le passé : le détail d'une session de la semaine
    dernière y lit son coefficient, à condition que le niveau marin de ce
    jour-là soit encore en base.
    """
    first = start or datetime.now(UTC).date()
    marks = await coefficients(db, first, days)

    by_day: dict[date, list[TideCoefficientMark]] = {}
    for mark in marks:
        by_day.setdefault(mark.ts.date(), []).append(
            TideCoefficientMark(
                ts=mark.ts,
                value=mark.value,
                approximate=mark.approximate,
                reason=mark.reason,
            )
        )

    return [
        TideCoefficientDay(day=day, marks=by_day[day]) for day in sorted(by_day)
    ]
