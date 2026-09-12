"""Matos — planches et combinaisons.

Petite table, deux points d'attention :

- **le compteur de sessions est calculé**, jamais stocké. Une colonne
  `session_count` se désynchronise à la première session supprimée, et il n'y
  a ici ni le volume ni la fréquence qui justifieraient un compteur dénormalisé ;
- **on ne supprime pas du matos qui a servi.** Le lien session ↔ planche est
  exactement ce que le modèle cherchera à apprendre (« proche de ta session du
  12/10, tu étais en 6'2 », cf. PROJET.md §7.2) ; le geste normal est de
  désactiver, ce qui sort la planche des pastilles de saisie sans toucher à
  l'historique.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.gear import Gear
from app.models.surf_session import SurfSession
from app.models.user import User
from app.schemas.gear import GearCreate, GearRead, GearUpdate, GearWithUsage
from app.services.auth_service import get_current_active_user

router = APIRouter(prefix="/gear", tags=["gear"])


async def _get_gear(db: AsyncSession, user_id: int, gear_id: int) -> Gear:
    result = await db.execute(
        select(Gear).where(Gear.id == gear_id).where(Gear.user_id == user_id)
    )
    gear = result.scalar_one_or_none()
    if gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Matos introuvable"
        )
    return gear


@router.get("", response_model=list[GearWithUsage])
async def list_gear(
    include_inactive: bool = Query(default=True),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[GearWithUsage]:
    """Le matos, avec son usure.

    Une seule requête d'agrégation pour tout le compteur, et pas une par ligne :
    `last_used_at` porte la présélection de l'écran de notation, et cet écran
    ne doit jamais attendre.
    """
    query = select(Gear).where(Gear.user_id == current_user.id)
    if not include_inactive:
        query = query.where(Gear.is_active.is_(True))

    result = await db.execute(query.order_by(Gear.is_active.desc(), Gear.name))
    items = list(result.scalars().all())
    if not items:
        return []

    usage = await db.execute(
        select(
            SurfSession.gear_id,
            func.count(SurfSession.id),
            func.max(SurfSession.started_at),
        )
        .where(SurfSession.user_id == current_user.id)
        .where(SurfSession.gear_id.in_([gear.id for gear in items]))
        .group_by(SurfSession.gear_id)
    )
    by_gear = {
        gear_id: (count, last) for gear_id, count, last in usage.all()
    }

    return [
        GearWithUsage(
            **GearRead.model_validate(gear).model_dump(),
            session_count=by_gear.get(gear.id, (0, None))[0],
            last_used_at=by_gear.get(gear.id, (0, None))[1],
        )
        for gear in items
    ]


@router.post("", response_model=GearRead, status_code=status.HTTP_201_CREATED)
async def create_gear(
    data: GearCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GearRead:
    gear = Gear(
        user_id=current_user.id,
        name=data.name.strip(),
        gear_type=data.gear_type.value,
        length_m=data.length_m,
        volume_l=data.volume_l,
        discipline=data.discipline.value,
        purchased_on=data.purchased_on,
    )
    db.add(gear)
    await db.commit()
    await db.refresh(gear)
    return GearRead.model_validate(gear)


@router.patch("/{gear_id}", response_model=GearRead)
async def update_gear(
    gear_id: int,
    data: GearUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> GearRead:
    gear = await _get_gear(db, current_user.id, gear_id)

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None and hasattr(value, "value"):
            value = value.value
        if field == "name" and isinstance(value, str):
            value = value.strip()
        setattr(gear, field, value)

    await db.commit()
    await db.refresh(gear)
    return GearRead.model_validate(gear)


@router.delete("/{gear_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gear(
    gear_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Supprime du matos qui n'a jamais servi. Les autres se désactivent.

    Refuser vaut mieux que supprimer en silence : le lien session ↔ planche est
    de la donnée d'apprentissage, et la perdre pour ranger une liste serait un
    mauvais échange. Le 409 dit quoi faire à la place.
    """
    gear = await _get_gear(db, current_user.id, gear_id)

    used: Optional[int] = (
        await db.execute(
            select(func.count(SurfSession.id)).where(SurfSession.gear_id == gear.id)
        )
    ).scalar_one()

    if used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{used} session(s) sur ce matos. Désactive-le plutôt : "
                "il sort des choix de saisie et l'historique reste intact."
            ),
        )

    await db.delete(gear)
    await db.commit()
