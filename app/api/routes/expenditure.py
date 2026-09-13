"""La dépense estimée du jour — surf et séances.

**Pourquoi un module à part, et pas une route de plus sous `/nutrition` :**
cette estimation ne sert pas qu'à la nutrition. Elle apparaît sur l'écran Jour,
qui mêle tous les domaines, et c'est là qu'on la regarde le matin. La ranger
sous `/nutrition` obligerait Jour à demander un écran qui n'est pas le sien,
et personne ne saurait plus où la chercher.

Le calcul, lui, est **le même** que celui qui alimente la cible calorique
(`services/nutrition.day_expenditure`). Un second calcul « pour l'affichage »
finirait par donner deux chiffres différents pour la même journée, et la seule
conclusion possible serait qu'on ne peut se fier à aucun des deux.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.user import User
from app.schemas.expenditure import DayExpenditureRead, ExpenditureItemRead
from app.services.auth_service import get_current_active_user
from app.services.nutrition import (
    DEFAULT_WEIGHT_KG,
    day_expenditure,
    latest_weight,
)

router = APIRouter(prefix="/expenditure", tags=["expenditure"])


def _zone(user: User) -> ZoneInfo:
    profile = user.profile
    try:
        return ZoneInfo(profile.timezone if profile else "Europe/Paris")
    except Exception:  # noqa: BLE001 — fuseau invalide en base
        return ZoneInfo("Europe/Paris")


@router.get("", response_model=DayExpenditureRead)
async def read_expenditure(
    day: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DayExpenditureRead:
    """Ce que la journée a coûté en plus de ne rien faire.

    Une journée est une notion **locale** : les bornes sont calculées dans le
    fuseau de l'utilisateur puis converties en UTC, comme partout ailleurs
    (cf. CLAUDE.md — dates en UTC en base, converties à l'affichage).
    """
    zone = _zone(current_user)
    target = day or datetime.now(zone).date()
    start = datetime.combine(target, time.min, tzinfo=zone).astimezone(UTC)
    end = start + timedelta(days=1)

    # Le poids retenu, dans l'ordre : la dernière pesée, puis le profil, puis
    # un défaut. Le dire est important — une estimation faite sur 75 kg par
    # défaut n'a pas la même valeur qu'une faite sur la pesée de dimanche.
    weight_kg = await latest_weight(db, current_user.id, target)
    profile = current_user.profile
    estimated = weight_kg is None
    if weight_kg is None:
        weight_kg = profile.weight_kg if profile else None
    if weight_kg is None:
        weight_kg = DEFAULT_WEIGHT_KG

    expenditure = await day_expenditure(
        db, current_user.id, target, weight_kg, start=start, end=end
    )

    return DayExpenditureRead(
        surf_min=expenditure.surf_min,
        # Arrondi à l'entier **ici**, une seule fois. La dépense est une
        # estimation : la rendre à la décimale suggérerait une précision que
        # ni le MET du compendium ni une durée arrondie au quart d'heure n'ont.
        surf_kcal=round(expenditure.surf_kcal),
        workout_min=expenditure.workout_min,
        workout_kcal=round(expenditure.workout_kcal),
        total_kcal=round(expenditure.total_kcal),
        items=[
            ExpenditureItemRead(
                kind=item.kind,
                label=item.label,
                minutes=item.minutes,
                met=item.met,
                kcal=round(item.kcal),
                detail=item.detail,
            )
            for item in expenditure.items
        ],
        weight_kg=round(weight_kg, 1),
        weight_estimated=estimated,
    )
