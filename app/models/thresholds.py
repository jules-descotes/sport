from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class UserThresholds(Base):
    """Les seuils de Jules — ce qui est « bon » pour lui, en chiffres.

    Décidé le 13/09 (retours n° 4). Jusque-là, le tableau horaire teintait ses
    cellules par **intensité** : plus la houle est grosse, plus c'est saturé.
    C'est juste, et c'est inutile — une houle de 3 m est grosse, ce qui n'est
    pas la même chose que bonne, et l'écran ne répondait donc jamais à la
    question qu'on lui pose en l'ouvrant.

    Ces huit nombres sont la réponse. Ils disent où commence le bon, et à
    partir d'où ça se gâte, **pour lui, sur ses spots** — la période s'améliore
    à partir de 8 s, le vent est parfait sous 10 nœuds, la houle commence à
    1,2 m. La rampe de couleur s'y accroche, et le score de démarrage aussi
    (`services/scoring.py`) : les deux lisaient jusqu'ici des bandes écrites en
    dur, c'est-à-dire l'avis de personne.

    **Une ligne par utilisateur, créée à la première lecture.** Pas de semis en
    migration : les valeurs par défaut vivent dans le code, où elles se
    corrigent, et une migration qui sème du contenu oblige à écrire une
    migration par changement d'avis.

    Les unités sont celles de la base — mètres, secondes, nœuds
    (cf. CLAUDE.md). Aucun « pied », aucun « km/h », et surtout aucune unité
    composite.
    """

    __tablename__ = "user_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Période, en secondes ───────────────────────────────────────────────
    # « De mieux en mieux à partir de 8 s. » En dessous, c'est du clapot et la
    # cellule reste neutre — un palier bas se lirait comme une petite quantité
    # de quelque chose de bien.
    period_good_s: Mapped[float] = mapped_column(Float, nullable=False)
    period_great_s: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Vent, en nœuds ────────────────────────────────────────────────────
    # Le seul axe **inversé** : moins il y en a, mieux c'est. D'où trois seuils
    # et pas deux — entre « top » et « injouable » il y a deux crans de gêne,
    # et les confondre ferait passer un 14 nœuds pour un coup de vent.
    wind_top_kt: Mapped[float] = mapped_column(Float, nullable=False)
    wind_strong_kt: Mapped[float] = mapped_column(Float, nullable=False)
    wind_very_strong_kt: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Houle, en mètres ──────────────────────────────────────────────────
    # « Ça commence à 1,2 m, puis mieux en grossissant. » `wave_big_m` n'est
    # pas un plafond de danger : c'est la taille où c'est le meilleur pour lui.
    # Au-delà, la note redescend d'elle-même.
    wave_min_m: Mapped[float] = mapped_column(Float, nullable=False)
    wave_good_m: Mapped[float] = mapped_column(Float, nullable=False)
    wave_big_m: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
