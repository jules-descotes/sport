from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
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
    # Mifflin-St Jeor a besoin de l'âge et du sexe (lot 5). Nullables : sans
    # eux, la cible calorique se rabat sur une estimation **et le dit**, plutôt
    # que d'inventer un âge. Un sexe inconnu prend la moyenne des deux
    # constantes — 166 kcal d'écart, du même ordre que ce que la calibration
    # rattrape en deux semaines.
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # `male`, `female`, ou nul.
    sex: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Le spot favori — **une seule prévision par défaut**, c'est la sienne qui
    # s'affiche sur Jour (décidé le 12/09 soir, cf. PROJET.md §11). C'est aussi
    # lui qui définit le niveau d'ingestion `home` : le job planifié ne connaît
    # que ce spot et les favoris secondaires. Tout le reste du catalogue ne
    # s'interroge que lorsqu'on le regarde, depuis l'écran Mer.
    #
    # `SET NULL` plutôt que `CASCADE` : supprimer un spot ne doit pas emporter
    # le profil, il doit juste rendre l'app muette jusqu'au prochain choix.
    home_spot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("spots.id", ondelete="SET NULL"), nullable=True
    )
    # Liste de valeurs de `Discipline` — surf seul au départ, foil ensuite.
    # Corrections manuelles du niveau d'entraînement, par groupe musculaire.
    # Une colonne JSON plutôt qu'une table : ce sont au plus huit entiers, ils
    # se lisent toujours ensemble, et une table coûterait une jointure à chaque
    # génération de séance. Absente ou vide = tout est déduit de l'historique
    # (cf. `services/workout_level.py`).
    training_levels: Mapped[Optional[dict]] = mapped_column(
        JSONVariant, nullable=True
    )

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
