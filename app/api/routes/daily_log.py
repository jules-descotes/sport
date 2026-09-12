"""Journal quotidien — trois secondes de swipe, y compris les jours sans session.

Sans les jours de renoncement, le modèle n'apprend que la moitié haute de la
distribution : ce sont les seuls exemples négatifs qu'il verra jamais
(cf. PROJET.md §5).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.daily_log import DailyLog
from app.models.spot import Spot
from app.models.user import User
from app.schemas.daily_log import DailyLogRead, DailyLogToday, DailyLogUpsert
from app.services.auth_service import get_current_active_user

router = APIRouter(prefix="/daily-log", tags=["daily-log"])


def _local_today(user: User) -> date:
    """« Aujourd'hui » au sens de l'utilisateur, pas au sens d'UTC.

    À 1 h du matin heure de Paris, UTC est encore la veille : sans cette
    conversion, le swipe du soir se rangerait dans la mauvaise journée.
    """
    timezone = user.profile.timezone if user.profile else "Europe/Paris"
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("Europe/Paris")
    return datetime.now(zone).date()


@router.get("/today", response_model=DailyLogToday)
async def read_today(
    day: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DailyLogToday:
    """La question du jour a-t-elle déjà été posée ?

    L'écran d'accueil masque la barre de swipe dès qu'il y a une réponse : une
    question déjà répondue qui reste affichée finit par ne plus être lue.
    """
    target = day or _local_today(current_user)
    result = await db.execute(
        select(DailyLog)
        .where(DailyLog.user_id == current_user.id)
        .where(DailyLog.day == target)
    )
    entry = result.scalar_one_or_none()

    return DailyLogToday(
        day=target,
        answered=entry is not None,
        entry=DailyLogRead.model_validate(entry) if entry else None,
    )


@router.post("", response_model=DailyLogRead, status_code=status.HTTP_200_OK)
async def upsert_daily_log(
    data: DailyLogUpsert,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DailyLogRead:
    """Enregistre la réponse du jour, ou la corrige.

    Idempotent volontairement : un double tap sur le parking ne doit pas créer
    deux lignes, et se tromper de bouton doit se rattraper d'un autre tap.
    """
    target = data.day or _local_today(current_user)

    if data.spot_id is not None:
        exists = await db.execute(select(Spot.id).where(Spot.id == data.spot_id))
        if exists.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Spot introuvable"
            )

    result = await db.execute(
        select(DailyLog)
        .where(DailyLog.user_id == current_user.id)
        .where(DailyLog.day == target)
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        entry = DailyLog(user_id=current_user.id, day=target)
        db.add(entry)

    entry.status = data.status.value
    entry.spot_id = data.spot_id
    entry.reason = data.reason

    await db.commit()
    await db.refresh(entry)
    return DailyLogRead.model_validate(entry)


@router.get("", response_model=list[DailyLogRead])
async def list_daily_log(
    since: Optional[date] = Query(default=None),
    until: Optional[date] = Query(default=None),
    limit: int = Query(default=90, gt=0, le=400),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[DailyLogRead]:
    query = select(DailyLog).where(DailyLog.user_id == current_user.id)
    if since is not None:
        query = query.where(DailyLog.day >= since)
    if until is not None:
        query = query.where(DailyLog.day <= until)

    result = await db.execute(query.order_by(DailyLog.day.desc()).limit(limit))
    return [DailyLogRead.model_validate(entry) for entry in result.scalars().all()]
