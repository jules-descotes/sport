"""Compteur d'appels journalier, par fournisseur — persisté en base.

Pourquoi en base et pas en mémoire : le conteneur Railway redémarre. Un
compteur en mémoire repartirait de zéro à chaque redéploiement, et le plafond
« 140 par jour » ne voudrait plus rien dire le jour où on pousse cinq fois.
C'est la même leçon que `run_ts` au lot 1 ter — ce qui doit survivre au
redémarrage vit dans Postgres.

Une ligne par `(provider, day)`, le jour en **UTC**. Le quota du Cerema se
remet à zéro selon *leur* journée, qu'on ne connaît pas ; d'où le plafond à 140
pour 150 accordées, qui absorbe le décalage.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ApiQuota(Base):
    __tablename__ = "api_quota"
    __table_args__ = (
        UniqueConstraint("provider", "day", name="uq_api_quota_provider_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # `candhis` aujourd'hui. La colonne existe pour que le prochain
    # fournisseur à quota n'ait pas besoin d'une deuxième table.
    provider: Mapped[str] = mapped_column(String, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
