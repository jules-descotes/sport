from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.db.types import JSONVariant
from app.models.enums import Discipline


class SurfSession(Base):
    """Une session à l'eau. Squelette posé au lot 1, formulaire au lot 2.

    Ce qui est irrattrapable après coup, c'est `conditions_snapshot` : il est
    figé à l'enregistrement, sous forme de **fenêtre T−2 h / T−1 h / T0**, en
    deux volets `forecast` et `observed`. Un point unique ne porte aucune
    tendance, et la tendance est un des signaux les plus forts (cf. CLAUDE.md,
    règle 7). Le volet `observed` est rempli depuis l'archive Open-Meteo, y
    compris pour un spot jamais ingéré et pour une session rétroactive.

    Deux notes distinctes, jamais une seule : une note unique mélange la houle
    et la forme du jour, et le modèle apprend du bruit.
    """

    __tablename__ = "surf_sessions"
    __table_args__ = (Index("ix_surf_sessions_user_started", "user_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    spot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spots.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Heure de début en UTC, comme tout le reste. La conversion en heure locale
    # est côté front, jamais en base.
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    discipline: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=Discipline.SURF.value,
        server_default=Discipline.SURF.value,
    )

    # Les deux notes, sur 5. Nulles tant que la session n'est pas notée : une
    # session enregistrée hors ligne sur le parking peut être notée plus tard.
    rating_conditions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_personal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    wave_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crowd: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Position réelle d'entrée à l'eau, quand la géoloc l'a fournie : elle peut
    # différer du point du spot de plusieurs centaines de mètres (pic, plage).
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    conditions_snapshot: Mapped[Optional[dict]] = mapped_column(
        JSONVariant, nullable=True
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
