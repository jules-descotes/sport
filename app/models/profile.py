from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import JSONVariant
from app.models.enums import Discipline

if TYPE_CHECKING:
    from app.models.user import User


class Profile(Base):
    """Mensurations et pratique. Unités en base : mètres et kilogrammes,
    jamais de composite (cf. CLAUDE.md).
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Liste de valeurs de `Discipline` — surf seul au départ, foil ensuite.
    disciplines: Mapped[list[str]] = mapped_column(
        JSONVariant, nullable=False, default=lambda: [Discipline.SURF.value]
    )
    # Fuseau d'affichage : les heures sont stockées en UTC, converties au rendu.
    timezone: Mapped[str] = mapped_column(
        String, nullable=False, default="Europe/Paris", server_default="Europe/Paris"
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

    user: Mapped["User"] = relationship(back_populates="profile")
