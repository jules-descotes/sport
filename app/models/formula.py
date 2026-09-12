from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
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
from app.db.types import JSONVariant
from app.models.exercise import Exercise


class Formula(Base):
    """Une **formule** — une séance type, pas un programme.

    Les cinq du document design (`docs/DESIGN-EXPLORATION.md` §3) plus leurs
    variantes. Chacune porte le **principe qui la justifie**, en une ligne :

    - c'est ce qui la distingue d'un programme copié ailleurs. On peut la
      défendre, la corriger, l'adapter, parce qu'on sait pourquoi elle est
      faite comme ça ;
    - et c'est ce qui se lit à l'écran quand on hésite entre deux.

    Les **variantes** existent pour une raison qui n'a rien de cosmétique : une
    formule faite tous les matins pendant six mois se fait de moins en moins
    bien, puis plus du tout. `variant_of` les groupe pour que l'avancement
    hebdomadaire se compte sur la famille et non sur chaque variante — trois
    Réveils différents dans la semaine, c'est trois réveils.
    """

    __tablename__ = "formulas"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_formulas_slug"),
        Index("ix_formulas_family", "variant_of"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    # Durée annoncée, en minutes. C'est une promesse : « 8 min » qui en prend
    # quinze ne se refait pas le lendemain matin.
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    # Séances visées par semaine. `0` = à la demande (Post-surf : après chaque
    # session, donc au rythme de la mer, pas du calendrier).
    weekly_target: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # La ligne qui justifie la formule. Obligatoire, et c'est délibéré.
    principle: Mapped[str] = mapped_column(Text, nullable=False)

    # Les `slug` d'objectifs servis. Une liste JSON plutôt qu'une table de
    # liaison : trois objectifs, jamais jointe, toujours lue en bloc.
    objective_slugs: Mapped[Optional[list]] = mapped_column(JSONVariant, nullable=True)
    # `morning` · `post_surf` · `core` · `mobility` · `strength`. Ce sont eux
    # que la proposition du jour regarde pour ne pas servir du renfo au
    # quatrième jour de surf d'affilée.
    tags: Mapped[Optional[list]] = mapped_column(JSONVariant, nullable=True)

    # `slug` de la formule de référence de la famille. Nul pour la principale.
    variant_of: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

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

    items: Mapped[list["FormulaItem"]] = relationship(
        back_populates="formula",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="FormulaItem.position",
    )

    @property
    def family(self) -> str:
        """Le `slug` de la famille — la formule elle-même, ou sa référence."""
        return self.variant_of or self.slug


class FormulaItem(Base):
    """Un exercice dans une formule, à sa place, avec sa dose.

    **Séries et répétitions, ou durée — jamais les deux.** Un gainage se tient
    quarante-cinq secondes ; une rotation thoracique se fait huit fois par
    côté. Forcer les deux dans le même champ obligerait le mode séance à
    deviner lequel compter, et il se tromperait.
    """

    __tablename__ = "formula_items"
    __table_args__ = (
        UniqueConstraint("formula_id", "position", name="uq_formula_item_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    formula_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("formulas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    sets: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # L'un **ou** l'autre, jamais les deux.
    reps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # « 3-1-3 » : trois secondes de descente, une de pause, trois de montée.
    # Une chaîne, pas trois entiers : c'est une notation, pas une grandeur.
    tempo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rest_s: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # « par côté », « jambes tendues » — la précision qui change l'exercice.
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    formula: Mapped["Formula"] = relationship(back_populates="items")
    # `selectin` : le mode séance lit la formule entière d'un coup, et va
    # devoir afficher le nom et l'image de chaque exercice sans réseau.
    exercise: Mapped["Exercise"] = relationship(lazy="selectin")
