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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.types import JSONVariant
from app.models.enums import Discipline, SessionStatus
from app.models.gear import Gear
from app.models.spot import Spot


class SurfSession(Base):
    """Une session à l'eau. Squelette posé au lot 1, saisie complète au lot 2.

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
    __table_args__ = (
        Index("ix_surf_sessions_user_started", "user_id", "started_at"),
        # L'écran Jour demande « y a-t-il une session à noter ? » à chaque
        # ouverture : sans cet index, c'est un balayage de tout l'historique.
        Index("ix_surf_sessions_user_status", "user_id", "status"),
        # Idempotence de la file hors ligne : le téléphone peut rejouer le même
        # envoi trois fois au retour du réseau, la base n'en garde qu'un.
        UniqueConstraint("user_id", "client_uuid", name="uq_surf_sessions_client_uuid"),
    )

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

    # `to_rate` tant que les deux notes ne sont pas posées. C'est ce qui permet
    # au chemin rapide de tenir en quinze secondes : on enregistre la session
    # sortie de l'eau, on la note au sec.
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=SessionStatus.TO_RATE.value,
        server_default=SessionStatus.TO_RATE.value,
    )

    # Les deux notes, sur 5. Nulles tant que la session n'est pas notée : une
    # session enregistrée hors ligne sur le parking peut être notée plus tard.
    rating_conditions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_personal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # La planche. `SET NULL` : désactiver du matos est le geste normal, le
    # supprimer est refusé tant qu'il porte des sessions — mais si la ligne
    # disparaît un jour, la session reste.
    gear_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("gear.id", ondelete="SET NULL"), nullable=True
    )

    wave_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crowd: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Photo de session, stockée sur R2 en production. L'URL, jamais le fichier.
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Identifiant fabriqué par le téléphone **avant** l'envoi. C'est lui qui
    # rend la file hors ligne rejouable sans risque : trois tentatives au
    # retour du réseau donnent une seule session.
    client_uuid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Vrai quand la session vient du chemin rapide : l'heure de début est alors
    # une estimation (fin − 90 min) que la notation corrige. Le distinguer
    # évite de prendre une estimation pour une mesure au moment d'analyser.
    start_estimated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )

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

    # `selectin` plutôt que le chargement paresseux par défaut : en SQLAlchemy
    # async, lire `session.spot` hors de la requête lève `MissingGreenlet`. Une
    # requête de plus par *page* (pas par ligne), et l'historique s'affiche
    # avec son spot et sa planche sans que chaque route ait à y penser.
    spot: Mapped["Spot"] = relationship(lazy="selectin")
    gear: Mapped[Optional["Gear"]] = relationship(lazy="selectin")

    @property
    def is_rated(self) -> bool:
        """Les **deux** notes, jamais une seule (cf. CLAUDE.md, règle 6).

        Une session notée sur les conditions mais pas sur le ressenti reste à
        noter : c'est justement le mélange des deux que la double note existe
        pour éviter.
        """
        return self.rating_conditions is not None and self.rating_personal is not None
