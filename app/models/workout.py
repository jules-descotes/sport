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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.exercise import Exercise
from app.models.formula import Formula


class WorkoutSession(Base):
    """Une séance faite — **et une séance écourtée est comptée à part**.

    C'est le point qui décide si ces lignes valent quelque chose. Une séance
    de 28 minutes arrêtée à la sixième est un renseignement : la formule est
    trop longue, ou mal placée dans la semaine, ou les deux. La compter comme
    une séance complète efface exactement l'information qui permettrait de la
    corriger — et la proposition du jour continuerait de la servir.

    Le `feeling` est le pendant de la note perso d'une session de surf : un
    seul chiffre, un écran, un tap, à la fin. Sans lui on ne saura jamais
    distinguer « j'ai arrêté parce que c'était trop dur » de « j'ai arrêté
    parce que j'étais en retard ».
    """

    __tablename__ = "workout_sessions"
    __table_args__ = (
        Index("ix_workout_sessions_user_started", "user_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # `SET NULL` : on peut retirer une formule du catalogue sans effacer les
    # séances qui l'ont suivie. La colonne `formula_name` garde le nom lisible.
    formula_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("formulas.id", ondelete="SET NULL"), nullable=True
    )
    # Figé à la création : une formule renommée ou retouchée ne doit pas
    # réécrire l'historique.
    formula_name: Mapped[str] = mapped_column(String(80), nullable=False)
    formula_family: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Terminée jusqu'au bout, ou arrêtée en route. Les deux sont enregistrées,
    # et elles ne se confondent jamais.
    completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    cut_short: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )

    feeling: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    formula: Mapped[Optional["Formula"]] = relationship(lazy="selectin")
    sets: Mapped[list["WorkoutSet"]] = relationship(
        back_populates="session",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="WorkoutSet.position",
    )

    @property
    def duration_min(self) -> Optional[int]:
        if self.ended_at is None:
            return None
        start = (
            self.started_at
            if self.started_at.tzinfo
            else self.started_at.replace(tzinfo=None)
        )
        return max(0, round((self.ended_at - start).total_seconds() / 60))


class WorkoutSet(Base):
    """Une série faite, passée ou écourtée.

    `skipped` distingue « je suis passé au suivant » de « je ne suis jamais
    arrivé jusque-là » : la première ligne existe avec `skipped=True`, la
    seconde n'existe pas du tout. Ce n'est pas la même information — l'une dit
    qu'un exercice ne passe pas, l'autre que la séance était trop longue.
    """

    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workout_session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # `SET NULL` sur les deux : un exercice retiré du catalogue ne doit pas
    # emporter l'historique des séances qui l'ont contenu.
    formula_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("formula_items.id", ondelete="SET NULL"), nullable=True
    )
    exercise_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("exercises.id", ondelete="SET NULL"), nullable=True
    )
    # Figé, comme `formula_name` : l'historique se lit sans jointure et sans
    # dépendre de ce que le catalogue est devenu.
    exercise_name: Mapped[str] = mapped_column(String(120), nullable=False)

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    skipped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["WorkoutSession"] = relationship(back_populates="sets")
    exercise: Mapped[Optional["Exercise"]] = relationship(lazy="selectin")
