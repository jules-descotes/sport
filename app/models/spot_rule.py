from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.db.types import JSONVariant


class SpotRule(Base):
    """Les critères de Jules pour un spot favori — larges, et tous optionnels.

    Décidé le 13/09. C'est l'*a priori* du §7.4 du PROJET.md, mais **c'est le
    sien** : « Parlementia marche en houle d'ouest de 1,2 à 2,5 m, période au
    moins 11 s, vent d'est, marée montante ». Ces phrases-là, aucun modèle ne
    les apprendra avant plusieurs saisons, et il les a déjà.

    Trois choses les distinguent d'un réglage de moteur, et elles sont
    délibérées :

    1. **Tout champ vide est une absence de contrainte**, jamais une valeur par
       défaut. On ne remplit pas les trous avec des seuils inventés : un spot
       dont on ne sait dire que « pas plus de 2 m » est décrit par cette seule
       ligne, et le reste du calcul générique continue de faire son travail.
    2. **Elles priment sur l'orientation calculée.** L'orientation vient du
       trait de côte OSM et ne sait rien du récif de Parlementia ni de la fosse
       de la Gravière (cf. PROJET.md §7.4). Quand Jules a posé des secteurs de
       houle, ce sont eux qui décident, et l'*a priori* géométrique s'efface.
    3. **Elles ne remplacent pas l'apprentissage, elles l'amorcent.** Le jour
       où un spot atteint ses vingt-cinq sessions notées, le modèle appris
       passe devant — exactement comme pour les features 10 et 11.

    Les secteurs sont des **listes de huit points** (N, NE, E, SE, S, SO, O,
    NO) et pas des angles : on ne saisit pas « 285° » sur une plage, on saisit
    « ouest ». La rose à seize points sert à lire, celle à huit à écrire.
    """

    __tablename__ = "spot_rules"
    __table_args__ = (
        # Un jeu de critères par utilisateur et par spot. L'utilisateur est
        # dans la clé dès maintenant : le jour où l'app s'ouvre aux potes
        # (PROJET.md §11), les critères de Jules ne doivent pas devenir ceux de
        # tout le monde — et ajouter la colonne après coup voudrait dire
        # rejouer une migration sur de la donnée saisie à la main.
        UniqueConstraint("user_id", "spot_id", name="uq_spot_rules_user_spot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    spot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spots.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Houle — en mètres, unité de base.
    wave_height_min_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wave_height_max_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Période moyenne minimale, en secondes. Pas de maximum : une longue
    # période n'a jamais gâché une session.
    wave_period_min_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Secteurs de houle acceptés, en huit points. Liste vide = pas de contrainte.
    swell_sectors: Mapped[list[str]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )

    # Vent — secteurs de provenance acceptés, et force maximale en nœuds.
    wind_sectors: Mapped[list[str]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )
    wind_max_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Phases de marée acceptées : `low`, `rising`, `high`, `falling`.
    tide_phases: Mapped[list[str]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )

    # Heures préférées, en heure **locale** — c'est la seule unité qui ait un
    # sens ici : « le matin » ne se saisit pas en UTC.
    hour_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hour_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
