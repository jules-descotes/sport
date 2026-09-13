from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SessionSegment(Base):
    """Une heure d'une session, notée à part.

    Décidé le 13/09 après deux jours d'usage. Une session de deux heures et
    demie n'est pas une note : la houle monte, le vent se lève, la marée
    tourne. Noter 3 en moyenne quand la première heure valait 5 et la dernière
    2, c'est effacer le seul signal que ces trois heures portaient — et c'est
    précisément ce que le modèle cherche à apprendre.

    **Chaque segment est un point d'apprentissage à part entière.** Il porte
    une heure pleine, donc il s'apparie à **sa** ligne horaire du
    `conditions_snapshot` — d'où l'extension de la fenêtre à toute la durée de
    la session, et pas seulement T−2 h → T0. Sans cette extension, les segments
    au-delà de la première heure n'auraient aucune condition à laquelle se
    rattacher, et ne vaudraient rien.

    **La note globale reste la référence d'affichage.** Les segments sont
    optionnels, ils ne remplacent rien : l'historique, Jour et les stats
    continuent de lire les deux notes de la session. Les segments servent le
    modèle, pas l'écran.

    Les deux notes sont stockées **en demi-points entiers** (×2), comme sur la
    session : voir `surf_session.py` pour le pourquoi.
    """

    __tablename__ = "session_segments"
    __table_args__ = (
        # Une heure ne se note qu'une fois. Re-noter remplace, ce qui est la
        # sémantique voulue et ce que `put` fait tout seul.
        UniqueConstraint(
            "session_id", "started_at", name="uq_session_segments_session_hour"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("surf_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Heure pleine, en UTC. C'est la clé d'appariement avec la ligne horaire du
    # snapshot : une heure à la minute près n'aurait rien à quoi se rattacher,
    # puisque Open-Meteo est horaire.
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    rating_conditions_half: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    rating_personal_half: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
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
