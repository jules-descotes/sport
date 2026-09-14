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
from app.db.types import JSONVariant


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
        # `run_ts` est **dans la clé**, et c'est tout l'objet du lot 1 ter : sans
        # lui, la passe du matin écrase la prévision émise la veille au soir, et
        # chaque jour d'ingestion est perdu définitivement (cf. PROJET.md §7.3).
        # Deux runs sur le même créneau coexistent donc, et la lecture
        # « dernière prévision » prend le `run_ts` max.
        UniqueConstraint(
            "spot_id",
            "ts",
            "source",
            "run_ts",
            name="uq_forecasts_spot_ts_source_run",
        ),
        # Lecture type : « les 5 prochains jours de ce spot ».
        Index("ix_forecasts_spot_ts", "spot_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("spots.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Heure prévue.
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Heure d'**émission** de la prévision, en UTC, arrondie à l'heure pleine.
    #
    # Open-Meteo ne publie pas l'heure de run de MFWAM : `run_ts` est donc
    # l'heure à laquelle *on* a capté cette prévision, ce qui est la grandeur
    # utile ici — elle date ce qu'on savait, et quand on le savait. L'arrondi à
    # l'heure garde l'idempotence intacte : le conteneur Railway redémarre, la
    # passe repart du début dix minutes plus tard, et elle retombe sur le même
    # run au lieu de dupliquer cent vingt lignes par spot.
    run_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

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

    # Sert de cache, et rien d'autre : au-delà de trois heures, on réinterroge.
    # Distinct de `run_ts`, qui est arrondi : la fraîcheur du cache se juge à la
    # minute, l'identité d'un run à l'heure.
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Observation(Base):
    """Mesure réelle — ce qui est *constaté*. Table distincte, et elle le reste.

    Prévision et mesure ne sont pas la même grandeur : la bouée n'existe pas
    dans le futur, elle ne peut donc pas entraîner le modèle moyen terme. Les
    mélanger dans un même vecteur de features, c'est du décalage train/serve,
    et ça ne se voit qu'en production (cf. PROJET.md §7.1).

    Créée vide au lot 1, remplie au lot 1 bis depuis CANDHIS (`getCampTR.php`,
    cf. `docs/CANDHIS.md`).
    """

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "ts", "source", name="uq_observations_station_ts_source"
        ),
        Index("ix_observations_spot_ts", "spot_id", "ts"),
        # Lecture type du bloc « Maintenant » : la dernière mesure d'une station.
        Index("ix_observations_station_ts", "station_id", "ts"),
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
    #
    # `hm0_m` reçoit `Hm0` **ou** `H1/3` selon le houlographe : deux estimateurs
    # très proches de la même grandeur, que la littérature échange couramment.
    # `raw` garde le libellé d'origine pour le jour où l'écart comptera.
    hm0_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wave_height_max_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    peak_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mean_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wave_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Étalement directionnel au pic : la houle est-elle rangée ou éparpillée.
    # Seuls les houlographes directionnels H13 le publient.
    directional_spread_deg: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    wind_speed_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_gust_kt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    water_temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # La ligne entière, appariée à son en-tête, telle que l'API l'a rendue.
    # Une colonne qu'on n'a pas su lire aujourd'hui reste récupérable sans
    # redemander douze mois d'archive à une API qui en accorde 150 par jour.
    raw: Mapped[Optional[dict]] = mapped_column(JSONVariant, nullable=True)
    # Le type de houlographe reconnu — même principe que `model_version` sur
    # `forecasts` : le jour où le format change, l'historique dit dans quelle
    # grammaire il a été écrit.
    format_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
