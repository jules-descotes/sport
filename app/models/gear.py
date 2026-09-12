from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.enums import Discipline, GearType


class Gear(Base):
    """Planches et combinaisons.

    `discipline` est ici **et** sur la session (cf. CLAUDE.md, règle 8) : une
    planche de foil et une planche de surf ne se comparent pas, et sans ce
    champ les notes se contredisent. Il sert aussi à ne proposer, au moment de
    noter, que le matos de la discipline de la session.

    La longueur est en **mètres**, pas en pieds et pouces. Un 6'2 est une unité
    composite — deux nombres et deux unités dans un seul champ — et le CLAUDE.md
    l'interdit en base. La conversion en pieds-pouces se fait à l'affichage,
    comme celle des heures UTC en heure locale : la base porte la grandeur, le
    front porte la coutume.
    """

    __tablename__ = "gear"
    __table_args__ = (
        # Lecture type de l'écran de notation : « mes planches actives ».
        Index("ix_gear_user_active", "user_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    gear_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=GearType.BOARD.value,
        server_default=GearType.BOARD.value,
    )
    # Nom court, et c'est une contrainte d'écran : il s'affiche en pastille sur
    # l'écran de notation, à côté de quatre autres, sur 390 px de large.
    name: Mapped[str] = mapped_column(String(40), nullable=False)

    length_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    discipline: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=Discipline.SURF.value,
        server_default=Discipline.SURF.value,
    )
    purchased_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Une planche cassée ou revendue sort des pastilles de saisie, mais reste
    # attachée à ses sessions passées : la supprimer perdrait le lien
    # conditions ↔ planche, qui est précisément ce qu'on cherche à apprendre.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
