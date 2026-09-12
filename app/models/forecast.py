from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Forecast(Base):
    """Prévision horaire — ce qui est *annoncé*.

    Unités en base : mètres, secondes, degrés, nœuds (cf. CLAUDE.md). Aucune
    conversion à l'affichage sauf les heures, stockées en UTC.

    `source` et `model_version` sont sur chaque ligne, et ce n'est pas du zèle :
    les modèles de vagues sont recalibrés tous les ans ou deux, et un biais qui
    change sans qu'on sache quand casse tout l'historique d'apprentissage
    (cf. PROJET.md §7.3).
    """

    __tablename__ = "forecasts"
    __table_args__ = (
        # Le cœur de l'idempotence : le conteneur Railway redémarre, le job
        # repart du début, et il ne duplique jamais une heure déjà ingérée.
        UniqueConstraint("spot_id", "ts", "source", name="uq_forecasts_spot_ts_source"),
        # Lecture type : « les 5 prochains jours de ce spot ».
        Index("ix_forecasts_spot_ts", "spot_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("spots.id", ondelete="CASCADE"),
        nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source: Mapped[str] = mapped_column(String, nullable=False, default="open-meteo")
    model: Mapped[str] = mapped_column(
        String, nullable=False, default="meteofrance_wave"
    )
    model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Houle totale
    wave_height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wave_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wave_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wave_peak_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Train de houle primaire
    swell_height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    swell_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    swell_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    swell_peak_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Train secondaire — features 16 et 17 du registre, stockées avant d'être
    # utilisées : on stocke large, on modélise étroit.
    secondary_swell_height_m: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    secondary_swell_direction_deg: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    secondary_swell_period_s: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Vent en nœuds, direction = provenance.
    wind_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_gust_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Marée : niveau de la mer par rapport au niveau moyen, en mètres. C'est un
    # modèle et pas une prédiction harmonique — à valider contre le SHOM avant
    # de s'y fier aveuglément (cf. PROJET.md §6).
    sea_level_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    water_temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Sert de cache : au-delà de trois heures, la ligne est réinterrogée.
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Observation(Base):
    """Mesure réelle — ce qui est *constaté*. Table distincte, et elle le reste.

    Prévision et mesure ne sont pas la même grandeur : la bouée n'existe pas
    dans le futur, elle ne peut donc pas entraîner le modèle moyen terme. Les
    mélanger dans un même vecteur de features, c'est du décalage train/serve,
    et ça ne se voit qu'en production (cf. PROJET.md §7.1).

    Créée vide au lot 1 : elle se remplira au lot 1 bis, à la réception du
    jeton CANDHIS.
    """

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "ts", "source", name="uq_observations_station_ts_source"
        ),
        Index("ix_observations_spot_ts", "spot_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Une bouée sert plusieurs spots : le rattachement est indicatif, la clé
    # naturelle reste la station.
    spot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("spots.id", ondelete="SET NULL"), nullable=True
    )
    station_id: Mapped[str] = mapped_column(String, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="candhis")

    # Hauteur significative et périodes, telles que les publie CANDHIS.
    hm0_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mean_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wave_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    wind_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_gust_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    water_temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
