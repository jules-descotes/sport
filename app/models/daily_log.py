from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.enums import DailyLogStatus


class DailyLog(Base):
    """Une ligne par jour, y compris — surtout — les jours sans session.

    Sans les jours où Jules a renoncé, le modèle n'apprend que la moitié haute
    de la distribution et ne sait pas reconnaître un mauvais jour. Ces jours-là
    sont les seuls exemples négatifs disponibles, et ils coûtent un swipe
    (cf. PROJET.md §5).

    Le jour est stocké en date locale et non en UTC : « le 12 septembre » est
    une notion humaine, pas un instant. Une session de 21 h heure locale le 12
    est bien une session du 12.
    """

    __tablename__ = "daily_log"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_log_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(String, nullable=False)

    # Spot envisagé : renseigné surtout quand on a regardé et renoncé — c'est
    # là que l'information est la plus utile au modèle.
    spot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("spots.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @staticmethod
    def is_valid_status(value: str) -> bool:
        return value in {s.value for s in DailyLogStatus}
