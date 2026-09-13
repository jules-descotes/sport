from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.db.types import JSONVariant
from app.models.enums import SpotSource, SpotTier, SpotType


class Spot(Base):
    """Catalogue mondial, importé d'OpenStreetMap et complété à la main.

    Le catalogue est mondial, l'ingestion ne l'est pas : c'est `tier` qui
    décide qui est interrogé, et le script d'import ne le touche jamais
    (cf. PROJET.md §6).
    """

    __tablename__ = "spots"
    __table_args__ = (
        # Clé naturelle de l'import mensuel : un objet OSM ne doit jamais être
        # inséré deux fois, quel que soit le nombre de rejeux.
        UniqueConstraint("osm_type", "osm_id", name="uq_spots_osm_object"),
        # `/spots/nearby` filtre d'abord sur une boîte englobante, puis calcule
        # la distance exacte en Python : sans cet index, c'est un balayage du
        # catalogue mondial à chaque ouverture de l'app.
        Index("ix_spots_lat_lon", "lat", "lon"),
        Index("ix_spots_tier", "tier"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    spot_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=SpotType.UNKNOWN.value,
        server_default=SpotType.UNKNOWN.value,
    )

    source: Mapped[str] = mapped_column(
        String, nullable=False, default=SpotSource.OSM.value
    )
    # `node`, `way` ou `relation` — nuls pour les spots ajoutés à la main.
    osm_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Les identifiants de nœuds OSM ont dépassé 2^31 depuis longtemps :
    # un Integer Postgres déborderait sur la moitié du catalogue.
    osm_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Orientation calculée depuis le trait de côte OSM, jamais saisie
    # (cf. CLAUDE.md, décidé le 12/09). `coast_bearing_deg` est le cap du trait
    # de côte lissé ; `onshore_dir_deg` sa normale sortante, c'est-à-dire la
    # direction d'où vient un vent onshore.
    coast_bearing_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    onshore_dir_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Distance au trait de côte retenu : au-delà de quelques centaines de
    # mètres, l'orientation devient douteuse et mérite d'être ignorée.
    coast_distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    webcam_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Niveau d'ingestion. Recalculé à chaque login, à chaque changement de
    # favoris et à chaque changement de position — jamais par l'import.
    tier: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=SpotTier.CATALOG.value,
        server_default=SpotTier.CATALOG.value,
    )
    # Miroir booléen de `tier != catalog`, tenu par `spot_tiers.recompute_tiers`.
    # Redondant, et c'est volontaire : le job planifié et les requêtes de
    # supervision filtrent dessus sans connaître la sémantique des niveaux.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )

    # Spot **technique**, pas un lieu de surf : le marégraphe de Brest, qui
    # sert le coefficient de marée national (cf. `services/tide_coefficient`).
    # Il reste `home` quoi que Jules mette en favori — ce n'est pas un favori,
    # c'est une source — et il est écarté de toutes les listes d'écran.
    is_reference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )

    # Étiquettes OSM brutes conservées telles quelles : la couverture est
    # inégale et on ne sait pas encore ce qui servira (surface, hazard, accès).
    osm_tags: Mapped[Optional[dict]] = mapped_column(JSONVariant, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SpotPreference(Base):
    """Rayon, favoris, masqués, domicile — une ligne par utilisateur.

    Les favoris sont une liste JSON plutôt qu'une table de liaison : ils sont
    plafonnés à vingt, toujours lus en bloc, et jamais joints. Une table de
    liaison coûterait une requête de plus à chaque écran pour zéro bénéfice.
    """

    __tablename__ = "spot_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    radius_km: Mapped[float] = mapped_column(
        Float, nullable=False, default=40.0, server_default="40"
    )
    home_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    home_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    favorite_spot_ids: Mapped[list[int]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )
    hidden_spot_ids: Mapped[list[int]] = mapped_column(
        JSONVariant, nullable=False, default=list
    )

    # Dernière position connue : elle élargit les spots « potentiels » quand on
    # est en déplacement, sans changer le domicile.
    last_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_position_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
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
