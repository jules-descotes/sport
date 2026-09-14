"""Les bouées — le catalogue des stations de mesure.

Une station n'est pas un spot, et elle n'a rien à faire dans la table `spots` :
un spot est un endroit où l'on surfe, une station est un instrument au large.
Elles se rejoignent par un rattachement — le plus proche, et sa distance — qui
vit sur le spot parce que c'est le spot qui a besoin de savoir qui le mesure.

Le catalogue vient de CANDHIS (`getCampListe.php` + `getCampInfos.php`) ; il est
rejouable et idempotent sur `code`, comme l'import OSM sur `(osm_type, osm_id)`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ObservationStation(Base):
    __tablename__ = "observation_stations"
    __table_args__ = (
        # Lecture type : « la station active la plus proche de ce point ».
        Index("ix_observation_stations_lat_lon", "lat", "lon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Le code de campagne CANDHIS : `06402` pour Anglet. Cinq caractères
    # alphanumériques, et le zéro de tête compte — d'où une chaîne et pas un
    # entier, qui en ferait 6402 au premier aller-retour.
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(
        String, nullable=False, default="candhis", server_default="candhis"
    )

    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sensor: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # `Actif` vient de `getCampListe.php`, et de nulle part ailleurs. C'est la
    # seule chose qui dise qu'une bouée est vivante : une liste écrite à la
    # main ici vieillirait le jour où une bouée part en carénage.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    is_directional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    # `0`, `1` ou `2` — le type de houlographe au sens de `getCampListe.php`.
    # Il décide de la forme de l'en-tête des mesures, donc de ce qu'on saura
    # lire : c'est une donnée de format, pas une étiquette.
    houlographe_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Le libellé rendu par l'API (« TR directionnel H13 »), gardé tel quel.
    data_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Dernière mesure effectivement écrite. Sert à repérer une bouée muette
    # sans compter les lignes de `observations` à chaque affichage.
    last_measured_at: Mapped[Optional[datetime]] = mapped_column(
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
