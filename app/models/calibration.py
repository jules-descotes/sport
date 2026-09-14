"""Prévision ↔ mesure — les paires de calibration (§7.3).

Une ligne = **une heure mesurée, vue par un run de prévision**. Une même heure
en produit donc plusieurs : celle annoncée trois jours avant, celle annoncée la
veille, celle annoncée le matin même. C'est exactement ce qu'on veut mesurer —
« de combien le modèle se trompe *à tel délai* » — et c'est ce que
l'historisation des runs du lot 1 ter a rendu possible.

> ⚠️ Cette table ne mélange rien : `forecasts` reste la prévision,
> `observations` reste la mesure, et celle-ci **les rapproche sans les
> confondre**. Aucune de ses colonnes n'entre dans un vecteur de features —
> c'est un tableau de bord, pas une source d'entraînement (cf. PROJET.md §7.1).

Le `lead_hours` est signé et toujours positif ici : un run postérieur à l'heure
cible n'est pas une prévision mais un constat déguisé, et il n'entre pas.
"""
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


class ForecastVsObserved(Base):
    __tablename__ = "forecast_vs_observed"
    __table_args__ = (
        # Une paire par (station, heure, run). Rejouer une passe ne doit rien
        # dupliquer — même exigence que `forecasts` et `observations`.
        UniqueConstraint(
            "station_id",
            "ts",
            "run_ts",
            name="uq_forecast_vs_observed_station_ts_run",
        ),
        # Lecture type : « les 30 derniers jours, par tranche de délai ».
        Index("ix_forecast_vs_observed_ts", "ts"),
        Index("ix_forecast_vs_observed_station_lead", "station_id", "lead_hours"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    station_id: Mapped[str] = mapped_column(String, nullable=False)
    # Le spot dont la prévision a été comparée — c'est lui qui porte le point
    # de grille du modèle, la station n'en a pas.
    spot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("spots.id", ondelete="SET NULL"), nullable=True
    )

    # L'heure cible, en UTC — l'heure mesurée.
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Le run qui l'avait annoncée.
    run_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # `ts - run_ts`, en heures. Stocké plutôt que recalculé : c'est la colonne
    # sur laquelle on agrège, et une différence de dates dans un `GROUP BY`
    # ne s'indexe pas.
    lead_hours: Mapped[float] = mapped_column(Float, nullable=False)

    forecast_hm0_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    observed_hm0_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forecast_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    observed_period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # La source et la version du modèle comparé, comme sur `forecasts` : le
    # jour où Météo-France recalibre MFWAM, le biais mesuré avant et après ne
    # décrit pas le même modèle, et les moyenner effacerait justement ce qu'on
    # cherchait à voir.
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Distance entre le spot et la bouée, en mètres — une comparaison à 25 km
    # ne vaut pas une comparaison à 4 km, et il faudra pouvoir le dire.
    distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
