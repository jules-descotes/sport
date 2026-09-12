"""Sessions de surf — squelette du lot 1.

L'endpoint existe ici pour une seule raison : c'est lui qui **fige le
`conditions_snapshot`**, et ce figeage est la seule décision de modèle
irrattrapable après coup. Le formulaire de saisie, le chemin rapide
(`POST /sessions/quick`), le matos et la file hors ligne arrivent au lot 2.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.spot import Spot
from app.models.surf_session import SurfSession
from app.models.user import User
from app.schemas.session import SurfSessionCreate, SurfSessionRead
from app.services.auth_service import get_current_active_user
from app.services.backfill import build_conditions_snapshot

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SurfSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SurfSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SurfSessionRead:
    """Enregistre une session et fige ses conditions.

    Fonctionne aussi pour une session rétroactive : l'archive Open-Meteo
    remonte la fenêtre T−2 h → T0 pour n'importe quelle date et n'importe quel
    spot du monde, ingéré ou non.

    Un échec de backfill n'empêche jamais l'enregistrement — le snapshot part
    avec un volet `observed` vide et une raison.
    """
    spot = (
        await db.execute(select(Spot).where(Spot.id == data.spot_id))
    ).scalar_one_or_none()
    if spot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spot introuvable"
        )

    session = SurfSession(
        user_id=current_user.id,
        spot_id=spot.id,
        started_at=data.started_at,
        duration_min=data.duration_min,
        discipline=data.discipline.value,
        rating_conditions=data.rating_conditions,
        rating_personal=data.rating_personal,
        wave_count=data.wave_count,
        crowd=data.crowd,
        notes=data.notes,
        lat=data.lat,
        lon=data.lon,
    )
    session.conditions_snapshot = await build_conditions_snapshot(
        db, spot, data.started_at
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SurfSessionRead.model_validate(session)


@router.get("", response_model=list[SurfSessionRead])
async def list_sessions(
    limit: int = Query(default=50, gt=0, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[SurfSessionRead]:
    result = await db.execute(
        select(SurfSession)
        .where(SurfSession.user_id == current_user.id)
        .order_by(SurfSession.started_at.desc())
        .limit(limit)
    )
    return [
        SurfSessionRead.model_validate(session) for session in result.scalars().all()
    ]
