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
