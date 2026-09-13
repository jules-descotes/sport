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
    # Posé par l'application elle-même, pas par un import ni par un humain :
    # aujourd'hui le seul est le marégraphe de Brest.
    SYSTEM = "system"


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


class GearType(StrEnum):
    """Ce qu'on emporte à l'eau. Deux catégories portent l'essentiel du signal.

    La **planche** est celle qui compte pour le modèle : à conditions égales, le
    voisin le plus proche dit aussi quelle planche prendre (cf. PROJET.md §7.2).
    La combinaison sert le conseil « quelle épaisseur » à partir de la
    température de l'eau, déjà présente dans les données Open-Meteo.
    """

    BOARD = "board"
    WETSUIT = "wetsuit"
    ACCESSORY = "accessory"


class SessionStatus(StrEnum):
    """Une session vit en deux temps, et c'est délibéré.

    Le chemin rapide (`POST /sessions/quick`, raccourci iPhone) enregistre une
    session en quinze secondes, sortie de l'eau, sans note. Elle est alors
    `to_rate` : l'écran Jour la remonte en premier, et la notation se fait plus
    tard, au sec. Séparer les deux moments est ce qui permet de tenir les
    quinze secondes — le risque du projet est la friction de saisie, pas la
    rareté des données (cf. PROJET.md §7.2).
    """

    TO_RATE = "to_rate"
    RATED = "rated"


# ── Le type de vagues (décidé le 13/09, retours n° 3) ──────────────────────
#
# Trois axes optionnels, saisis à la notation. **Ce sont des descripteurs des
# conditions observées, pas des étiquettes de confort** : ils décrivent ce
# qu'ont fait les vagues, comme le fait `conditions_snapshot`, à ceci près
# qu'aucune API ne les mesure et que seul quelqu'un dans l'eau peut les dire.
#
# D'où leur intérêt au lot 3 : ils sont exploitables comme **cibles
# auxiliaires**. Prédire « creuse » depuis la période, la cambrure et le vent
# est une tâche apprenable sur beaucoup moins d'exemples qu'une note de goût,
# et un modèle qui apprend d'abord à décrire la mer arrive mieux armé pour la
# noter. Ils ne doivent donc **jamais** entrer comme *entrées* du modèle
# moyen terme : ils ne sont pas disponibles au moment de la prédiction
# (cf. CLAUDE.md, règle 11).
#
# Trois valeurs par axe, pas cinq : on les saisit une main sur la planche,
# et personne ne sait départager « assez creuse » de « plutôt creuse ».


class WaveSize(StrEnum):
    """Taille ressentie. Distincte du Hm0 du modèle, et c'est le but.

    Le modèle donne une hauteur de houle au large ; ce champ dit ce qui a
    déferlé. L'écart entre les deux est une information sur le spot.
    """

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class WaveLength(StrEnum):
    """Longueur des vagues — la distance qu'on peut faire dessus.

    `SHORT` / `MEDIUM` / `LONG`, et pas une longueur d'onde : c'est un
    ressenti de glisse, pas une grandeur physique.
    """

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class WaveShape(StrEnum):
    """Forme du déferlement.

    `HOLLOW` creuse · `MUSHY` molle · `CRUMBLING` déferlante (qui casse par
    l'épaule sans tube ni mollesse).
    """

    HOLLOW = "hollow"
    MUSHY = "mushy"
    CRUMBLING = "crumbling"
