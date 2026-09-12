from __future__ import annotations

from enum import StrEnum


class Discipline(StrEnum):
    """Portée par la session ET par le matos (cf. CLAUDE.md, règle 8).

    Les conditions idéales en foil sont quasi l'inverse du surf : sans ce champ,
    les notes se contredisent et le modèle n'apprend rien.
    """

    SURF = "surf"
    FOIL = "foil"
    LONGBOARD = "longboard"


class SurfLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class SpotSource(StrEnum):
    """`osm` est réimporté tous les mois, `user` ne l'est jamais.

    Le script d'import ne doit sous aucun prétexte écraser un spot ajouté à la
    main depuis la carte : c'est la seule donnée du catalogue qui n'est pas
    reconstituable.
    """

    OSM = "osm"
    USER = "user"


class SpotType(StrEnum):
    BEACH = "beach"
    REEF = "reef"
    POINT = "point"
    UNKNOWN = "unknown"


class SpotTier(StrEnum):
    """Le niveau d'ingestion, et rien d'autre (cf. PROJET.md §6).

    home      — favoris, ingestion planifiée toutes les 3 h
    potential — dans le rayon ou près de la dernière position, à la demande
    catalog   — le reste du monde, jamais ingéré
    """

    HOME = "home"
    POTENTIAL = "potential"
    CATALOG = "catalog"


class DailyLogStatus(StrEnum):
    """Trois secondes de swipe par jour, y compris les jours sans session.

    `WATCHED_AND_PASSED` et `NOT_WATCHED` sont les seuls exemples négatifs dont
    le modèle disposera jamais (cf. PROJET.md §5).
    """

    SURFED = "surfed"
    WATCHED_AND_PASSED = "watched_and_passed"
    NOT_WATCHED = "not_watched"
