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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Objective(Base):
    """Un objectif **mesuré** — pas une intention, un nombre.

    C'est la table que `PROJET.md` §5 ne prévoyait pas et que l'exploration
    ergonomique a fait apparaître (`docs/DESIGN-EXPLORATION.md` §3) : sans
    mesure datée, le training est une liste de bonnes résolutions, et l'écran
    Training n'a rien à afficher. Avec elle, il a trois jauges, et la formule
    du jour se choisit toute seule — c'est celle qui sert l'objectif le plus en
    retard.

    `direction` dit dans quel sens on progresse, et il faut le dire : « mains
    au sol » va de −14 cm vers 0, donc **vers le haut** ; un jour où l'on
    ajoutera un tour de taille, il ira vers le bas. Sans cette colonne, la
    jauge afficherait un recul comme un progrès sur la moitié des objectifs.

    La valeur de départ n'est **pas** saisie : c'est la première mesure. Un
    départ tapé au clavier est une estimation qu'on prendra ensuite pour une
    mesure, et c'est exactement ce que cette table existe pour éviter.
    """

    __tablename__ = "objectives"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_objectives_user_slug"),
        Index("ix_objectives_user_active", "user_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Ce qu'on mesure, en toutes lettres : « distance mains-sol, jambes
    # tendues ». Une mesure qu'on ne sait pas refaire à l'identique ne se
    # compare pas à elle-même.
    measure: Mapped[str] = mapped_column(Text, nullable=False)
    # Unité de base, jamais composite (cf. CLAUDE.md) : `cm`, `deg`, `s`.
    # Le « 2:10 » de gainage est un affichage, comme le 6'2 d'une planche.
    unit: Mapped[str] = mapped_column(String(12), nullable=False)

    # `up` = plus c'est haut, mieux c'est. `down` = l'inverse.
    direction: Mapped[str] = mapped_column(
        String(4), nullable=False, default="up", server_default="up"
    )
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Rappel de mesure. Deux à trois semaines : en dessous, on mesure du bruit
    # de mesure ; au-dessus, on perd le fil.
    measure_every_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=21, server_default="21"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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

    # `selectin` : l'écran Training lit les trois jauges d'un coup, et lire
    # `objective.measurements` hors requête lèverait `MissingGreenlet` en
    # SQLAlchemy async.
    measurements: Mapped[list["ObjectiveMeasurement"]] = relationship(
        back_populates="objective",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ObjectiveMeasurement.measured_on",
    )

    @property
    def start_value(self) -> Optional[float]:
        """La **première** mesure, jamais une valeur saisie à la main."""
        return self.measurements[0].value if self.measurements else None

    @property
    def current_value(self) -> Optional[float]:
        """La dernière mesure en date."""
        return self.measurements[-1].value if self.measurements else None

    @property
    def last_measured_on(self) -> Optional[date]:
        return self.measurements[-1].measured_on if self.measurements else None


class ObjectiveMeasurement(Base):
    """Une mesure datée. Une par jour et par objectif, au plus.

    Mesurer deux fois le même jour donne deux chiffres différents pour la même
    chose : on garde le dernier, ce qui est la lecture la plus naturelle (« je
    me suis remesuré, c'était mal fait la première fois »).
    """

    __tablename__ = "objective_measurements"
    __table_args__ = (
        UniqueConstraint(
            "objective_id", "measured_on", name="uq_objective_measurement_day"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    objective_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("objectives.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Une date locale, pas un instant : on ne mesure pas sa souplesse à la
    # seconde près, et « le 12 septembre » est ce qu'on veut relire.
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    objective: Mapped["Objective"] = relationship(back_populates="measurements")
