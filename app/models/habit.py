"""Suivi d'habitudes quotidiennes — compteurs libres, ton neutre.

Décidé le 13/09. Deux règles gouvernent ce modèle, et elles ne sont pas
négociables :

1. **Aucun jugement, nulle part.** Pas de « série perdue », pas de rouge, pas de
   pourcentage de réussite stocké. Un compteur et des événements horodatés. Ce
   qui se calcule à l'affichage est une **tendance**, jamais une note. Une
   application qui gronde est une application qu'on désinstalle, et un compteur
   qu'on a cessé d'ouvrir ne mesure plus rien.
2. **Les événements sont horodatés à la seconde.** Pas une colonne par jour :
   l'intérêt de ces données au lot 6 est de les croiser avec le **ressenti des
   sessions du lendemain**, et un croisement se fait sur des instants. Une
   agrégation par jour posée aujourd'hui détruirait cette possibilité pour
   toujours.

Une habitude se **met en pause**, elle ne se supprime pas : les événements
passés sont de la donnée, et une envie du dimanche soir ne doit pas pouvoir
effacer trois mois de comptage.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
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


class Habit(Base):
    """Un compteur libre, défini par Jules.

    `kind` vaut `count` (combien de fois) ou `check` (fait ou pas fait). Les
    deux vivent dans la même table parce qu'un « oui/non » est un compteur
    plafonné à un, et que les séparer ferait deux écrans pour un seul geste.
    """

    __tablename__ = "habits"
    __table_args__ = (Index("ix_habits_user_active", "user_id", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Une icône **parmi une petite liste** (`lib/habit-icons.ts`), pas une URL
    # ni un emoji : les icônes du produit sont en trait de 1,75 px, dessinées
    # sur une grille de 24, et jamais d'emoji (cf. CLAUDE.md).
    icon: Mapped[str] = mapped_column(String(24), nullable=False, default="check")
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="count")
    # Libre : « verres », « minutes », « fois ». Vide pour un oui/non.
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Objectif **optionnel**, et c'est tout l'esprit : une habitude sans
    # objectif est une habitude qu'on observe, pas qu'on se fixe.
    target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # `day` ou `week`.
    target_period: Mapped[str] = mapped_column(
        String(10), nullable=False, default="day", server_default="day"
    )

    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # En pause : l'habitude disparaît de l'écran Jour, ses événements restent.
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


class HabitEvent(Base):
    """Un tap. Horodaté à la seconde, et c'est volontaire.

    L'intérêt de ces lignes au lot 6 sera de les croiser avec le ressenti des
    sessions du lendemain : « les jours où j'ai bu trois verres, je note ma
    forme un point en dessous ». Un tel croisement se fait sur des instants.
    Agréger par jour dès maintenant détruirait cette possibilité pour toujours,
    et c'est le genre de décision qu'on ne peut pas reprendre après coup —
    comme le `conditions_snapshot` d'une session.
    """

    __tablename__ = "habit_events"
    __table_args__ = (
        Index("ix_habit_events_habit_at", "habit_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    habit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("habits.id", ondelete="CASCADE"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Un par tap, en général. Négatif pour corriger un tap de trop : on annule
    # en ajoutant l'inverse plutôt qu'en supprimant, parce qu'une correction
    # est elle-même une information — le geste a eu lieu.
    quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1"
    )
    note: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
