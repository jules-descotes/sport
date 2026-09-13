"""Ranger 1 700 exercices sans en inventer un seul — et les dire en français.

Décidé le 13/09 (retours n° 3 et n° 4). Deux besoins qui tiennent ensemble :

- le **générateur de séances** a besoin de savoir ce qu'est un exercice — quel
  groupe il travaille, quel mouvement il fait, avec quoi, et à quel point c'est
  dur ;
- l'**écran** a besoin de le dire en français, avec une image.

Les deux se heurtent au même mur : les 1 661 exercices importés viennent de
bases anglophones, et personne ne les a relus. D'où la règle qui gouverne tout
ce module :

> **Ce qui n'est pas reconnu reste « à classer ». Jamais deviné.**

C'est la leçon de `sport=surfing`, appliquée une seconde fois : une étiquette
plausible posée en masse sur des données qu'on n'a pas regardées produit un
catalogue qui a l'air juste et qui ne l'est pas. Un exercice « à classer » est
inutile au générateur ; un exercice mal classé lui fait proposer un soulevé de
terre en séance de mobilité, et c'est bien pire.

Le classement se relit avant d'être écrit : `python -m scripts.import_exercises
--sample 40` montre quarante lignes classées et **n'écrit rien**.

**Le français n'est pas de la traduction automatique.** Les noms viennent, dans
l'ordre : du champ `translations` de wger quand il existe (traduit par des
humains, sous licence libre), puis d'un glossaire déterministe écrit ici. Ce
qui ne tombe dans aucun des deux garde `name_fr` à NULL — et un exercice sans
nom français n'entre ni dans le générateur ni dans une formule. Un « Barbell
Hip Thrust » au milieu d'une séance ne se lit pas à bout de bras.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

# ── Ce qui n'est pas reconnu ───────────────────────────────────────────────
#
# Une valeur, pas un `None` : « à classer » est un état qu'on peut compter,
# filtrer et corriger. Un `NULL` se confondrait avec « pas encore importé ».
UNCLASSIFIED = "a-classer"


# ── Groupes musculaires ────────────────────────────────────────────────────
#
# Les huit du 13/09. Volontairement grossiers : Jules compose « des abdos »,
# pas « du transverse ». Un découpage fin se vérifie mal et ne sert personne.

GROUPS = (
    "abdos",
    "dos",
    "epaules",
    "jambes",
    "hanches",
    "poitrine",
    "bras",
    "corps-entier",
)

GROUP_LABELS = {
    "abdos": "Abdos",
    "dos": "Dos",
    "epaules": "Épaules",
    "jambes": "Jambes",
    "hanches": "Hanches",
    "poitrine": "Poitrine",
    "bras": "Bras",
    "corps-entier": "Corps entier",
    UNCLASSIFIED: "À classer",
}

# Anglais **et** français : la moitié du catalogue vient de bases anglophones,
# l'autre est écrite ici. Deux dictionnaires divergeraient.
# **L'ordre compte, ici aussi.** « Back Squat » contient « back » : lu dans
# l'ordre alphabétique, il partirait dans le dos. Les groupes dont le nom est le
# plus souvent un faux ami — le dos — passent donc après ceux qui portent un
# mouvement sans ambiguïté.
GROUP_WORDS: dict[str, tuple[str, ...]] = {
    "abdos": (
        "abdominal", "abdominals", "abs", "core", "oblique", "obliques",
        "crunch", "plank", "hollow", "waist", "transverse",
        "abdos", "abdominaux", "gainage", "ceinture abdominale", "obliques",
    ),
    "jambes": (
        "quadriceps", "quads", "hamstring", "hamstrings", "calf", "calves",
        "leg", "legs", "squat", "lunge", "leg press", "leg curl",
        "jambe", "jambes", "quadriceps", "ischio", "ischio-jambiers",
        "mollet", "mollets", "fente", "fentes",
    ),
    "hanches": (
        "hip", "hips", "glute", "glutes", "abductor", "adductor",
        "hip flexor", "psoas", "piriformis", "pigeon",
        "hanche", "hanches", "fessier", "fessiers", "psoas", "adducteurs",
    ),
    "poitrine": (
        "chest", "pectoral", "pectorals", "pecs", "bench press", "push-up",
        "pushup", "push up", "fly", "dip", "dips",
        "poitrine", "pectoraux", "pompe", "pompes",
    ),
    "epaules": (
        "shoulder", "shoulders", "deltoid", "delts", "rotator cuff",
        "overhead press", "lateral raise", "front raise", "face pull",
        "epaule", "epaules", "deltoides", "coiffe",
    ),
    "bras": (
        "biceps", "triceps", "forearm", "forearms", "brachialis", "curl",
        "bras", "avant-bras", "biceps", "triceps", "flexion des bras",
    ),
    # Après « jambes » et « hanches » : « Back Squat » et « Hip Thrust »
    # contiennent « back » et « hip », et ce ne sont ni l'un ni l'autre des
    # exercices de dos.
    "dos": (
        "lat", "lats", "latissimus", "trapezius", "traps", "rhomboid",
        "erector spinae", "lower back", "upper back", "middle back", "back",
        "row", "pulldown", "pull-up", "pullup", "chin-up",
        "dos", "dorsaux", "trapezes", "lombaires", "chaine posterieure",
        "tirage", "traction",
    ),
    "corps-entier": (
        "full body", "total body", "burpee", "clean", "snatch", "thruster",
        "turkish get-up", "get up", "bear crawl", "farmer",
        "corps entier", "burpee", "arrache", "epaule-jete", "portage",
    ),
}


# ── Patterns de mouvement ──────────────────────────────────────────────────
#
# Les douze du 13/09. C'est **le pattern qui fait la séance**, plus que le
# groupe : trois exercices de tirage d'affilée font une séance de tirage, quel
# que soit le muscle visé. Le générateur s'en sert pour varier — et pour ne pas
# proposer trois gainages statiques de suite en appelant ça un circuit.

PATTERNS = (
    "gainage-statique",
    "anti-rotation",
    "flexion",
    "extension",
    "poussee",
    "tirage",
    "squat",
    "fente",
    "charniere",
    "portage",
    "mobilite",
    "etirement",
)

PATTERN_LABELS = {
    "gainage-statique": "Gainage statique",
    "anti-rotation": "Anti-rotation",
    "flexion": "Flexion",
    "extension": "Extension",
    "poussee": "Poussée",
    "tirage": "Tirage",
    "squat": "Squat",
    "fente": "Fente",
    "charniere": "Charnière",
    "portage": "Portage",
    "mobilite": "Mobilité",
    "etirement": "Étirement",
    UNCLASSIFIED: "À classer",
}

# **L'ordre compte.** Les motifs les plus spécifiques d'abord : « side plank »
# doit tomber sur le gainage statique et pas sur l'anti-rotation, et « pallof
# press » sur l'anti-rotation et pas sur la poussée. Un dictionnaire ordonné,
# lu de haut en bas, est plus lisible qu'un score de pertinence — et il se
# corrige ligne par ligne quand l'échantillon montre une erreur.
PATTERN_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "anti-rotation",
        (
            "pallof", "anti-rotation", "anti rotation", "renegade row",
            "suitcase", "bird dog", "bird-dog", "dead bug", "deadbug",
            "dead-bug", "chien d'arret", "bird dog",
        ),
    ),
    (
        "gainage-statique",
        (
            "plank", "hollow hold", "hollow body", "l-sit", "wall sit",
            "isometric", "hold", "bridge hold", "superman hold",
            "gainage", "planche ventrale", "planche laterale", "chaise",
        ),
    ),
    (
        # Les mobilités **nommées**, avant le mot « stretch » qui les suit
        # souvent : « Cat Cow Stretch » est un chat-vache, pas un étirement
        # quelconque, et le générateur s'en sert pour ouvrir une séance.
        "mobilite",
        (
            "cat cow", "cat-cow", "thoracic rotation", "shoulder dislocate",
            "arm circle", "downward dog", "down dog", "world's greatest",
            "90 90", "hip circle", "leg swing", "inchworm",
            "chat-vache", "rotation thoracique", "passage de baton",
            "chien tete en bas",
        ),
    ),
    (
        "etirement",
        (
            "stretch", "stretching", "static stretch", "pnf",
            "etirement", "etirements", "assouplissement",
        ),
    ),
    (
        "mobilite",
        (
            "mobility", "warm up", "warmup", "cat cow", "cat-cow",
            "thoracic rotation", "shoulder dislocate", "arm circle",
            "foam roll", "smr", "yoga", "dynamic",
            "mobilite", "chat-vache", "rotation thoracique", "passage de baton",
            "cercle de bras", "chien tete en bas", "pigeon", "cobra",
        ),
    ),
    (
        "charniere",
        (
            "deadlift", "romanian", "rdl", "good morning", "hip hinge",
            "hip thrust", "glute bridge", "kettlebell swing", "swing",
            "clean", "snatch", "power clean", "hang clean",
            "souleve de terre", "charniere", "pont fessier", "epaule jete",
        ),
    ),
    (
        "squat",
        (
            "squat", "leg press", "step up", "step-up", "box jump",
            "accroupi", "flexion de jambes",
        ),
    ),
    (
        "fente",
        (
            "lunge", "split squat", "bulgarian", "curtsy",
            "fente", "fentes",
        ),
    ),
    (
        "tirage",
        (
            "row", "bench pull", "pull-up", "pullup", "pull up", "chin-up",
            "chinup", "pulldown", "pull down", "face pull", "shrug", "curl",
            "pullover", "high pull",
            "tirage", "traction", "rowing", "flexion des bras",
        ),
    ),
    (
        "poussee",
        (
            "press", "push-up", "pushup", "push up", "dip", "dips",
            "bench", "fly", "flye", "kickback", "skullcrusher", "pushdown",
            "push down", "burpee", "triceps extension", "overhead extension",
            "pompe", "pompes", "developpe", "dips",
        ),
    ),
    (
        "portage",
        (
            "farmer", "carry", "waiter walk", "suitcase carry", "bear crawl",
            "portage", "marche du fermier",
        ),
    ),
    (
        "flexion",
        (
            "crunch", "sit-up", "situp", "sit up", "leg raise",
            "hanging leg raise", "knee raise", "v-up", "toes to bar",
            "mountain climber",
            "releve de jambes", "releves de jambes", "flexion du tronc",
        ),
    ),
    (
        "extension",
        (
            "back extension", "hyperextension", "superman", "reverse hyper",
            "calf raise", "lateral raise", "front raise", "rear delt raise",
            "extension lombaire", "extension du dos", "extension des mollets",
            "elevation laterale", "elevation frontale",
        ),
    ),
)


# ── Matériel ───────────────────────────────────────────────────────────────
#
# Six catégories, et une seule vraiment décisive : **aucun**. C'est elle qui
# décide si une séance est faisable sur le parking de la plage, et c'est la
# demande la plus fréquente du générateur.

EQUIPMENTS = (
    "aucun",
    "elastique",
    "halteres",
    "barre-traction",
    "kettlebell",
    "machine",
)

EQUIPMENT_LABELS = {
    "aucun": "Aucun",
    "elastique": "Élastique",
    "halteres": "Haltères",
    "barre-traction": "Barre de traction",
    "kettlebell": "Kettlebell",
    "machine": "Machine",
    UNCLASSIFIED: "À classer",
}

# Ordonné : une ligne peut dire « band » et « dumbbell », et l'élastique
# l'emporte parce qu'il suffit — c'est le matériel le plus léger qui décide de
# la faisabilité.
EQUIPMENT_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        # En premier : « body only » est une **affirmation** de la base
        # d'origine, pas une absence d'information. Vérifié sur l'échantillon —
        # sans cette priorité, l'indice « poids du corps » d'une planche
        # latérale tombait sur « haltères » à cause du mot « poids ».
        "aucun",
        (
            "body only", "bodyweight", "body weight", "no equipment",
            "poids du corps", "sans materiel", "aucun materiel",
        ),
    ),
    (
        "barre-traction",
        ("pull-up bar", "pullup bar", "chin-up bar", "barre de traction"),
    ),
    (
        "elastique",
        ("band", "bands", "resistance band", "tube", "elastique", "bande"),
    ),
    (
        "kettlebell",
        ("kettlebell", "kettlebells", "kb", "kettlebell"),
    ),
    (
        "halteres",
        (
            "dumbbell", "dumbbells", "barbell", "e-z curl bar", "ez bar",
            "plate", "weighted", "medicine ball", "haltere", "halteres",
            "barre", "barre chargee",
        ),
    ),
    (
        "machine",
        (
            "machine", "cable", "smith", "lever", "sled", "hammer strength",
            "leg press", "pulley", "poulie", "machine",
        ),
    ),
)


# ── Difficulté ─────────────────────────────────────────────────────────────
#
# De 1 à 5. Elle n'est **pas** devinée du nom : un « push-up » et un
# « one-arm push-up » portent le même mot. Elle vient du niveau annoncé par la
# base quand il existe, et d'un petit nombre de marqueurs sans ambiguïté
# sinon. Le reste retombe sur 3 — le milieu — et c'est assumé : une difficulté
# fausse fait proposer une séance infaisable, mais une difficulté absente
# empêcherait le générateur de fonctionner du tout.
DEFAULT_DIFFICULTY = 3

LEVEL_DIFFICULTY = {
    "beginner": 2,
    "novice": 2,
    "intermediate": 3,
    "advanced": 4,
    "expert": 5,
    "elite": 5,
    "debutant": 2,
    "intermediaire": 3,
    "avance": 4,
}

# Marqueurs sans ambiguïté, dans les deux sens.
EASIER_WORDS = (
    "assisted", "kneeling", "wall", "incline push", "banded assist",
    "assiste", "a genoux", "au mur", "facilite",
)
HARDER_WORDS = (
    "one arm", "one-arm", "single arm", "single-arm", "one leg", "one-leg",
    "single leg", "single-leg", "pistol", "archer", "front lever",
    "muscle-up", "muscle up", "deficit", "weighted", "explosive", "plyo",
    "jump", "clap",
    "une main", "un bras", "une jambe", "leste", "saute", "explosif",
)


# ── Temps ou répétitions ───────────────────────────────────────────────────

EFFORT_TIME = "temps"
EFFORT_REPS = "reps"

# Ce qui se **tient** plutôt que de se compter. Le pattern suffit à trancher
# dans la quasi-totalité des cas, et c'est plus sûr que de lire le nom.
TIME_PATTERNS = ("gainage-statique", "etirement", "mobilite", "portage")


# ── Unilatéral ─────────────────────────────────────────────────────────────
#
# « Par côté » change la durée d'une séance du simple au double. C'est la seule
# raison pour laquelle cette colonne existe : le générateur doit savoir qu'une
# fente à une jambe coûte deux fois le temps annoncé.
UNILATERAL_WORDS = (
    "one arm", "one-arm", "single arm", "single-arm", "one leg", "one-leg",
    "single leg", "single-leg", "alternating", "each side", "per side",
    "unilateral", "split squat", "bulgarian", "side plank", "pallof",
    "suitcase", "bird dog", "bird-dog", "dead bug", "deadbug", "curtsy",
    "par cote", "un bras", "une jambe", "alterne", "alternees",
    "planche laterale", "pigeon", "fente",
)


def normalize(text: str) -> str:
    """Minuscules, sans accent, ponctuation réduite à des espaces.

    Le même traitement pour l'anglais et le français : c'est ce qui permet à un
    seul dictionnaire de motifs de lire « ischio-jambiers » et « hamstrings ».
    """
    stripped = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    stripped = stripped.lower()
    stripped = re.sub(r"[^a-z0-9]+", " ", stripped)
    return f" {stripped.strip()} "


def _hit(haystack: str, words: Iterable[str]) -> bool:
    """Le motif est-il dans la chaîne ? **Pluriel compris.**

    Les bases ouvertes écrivent « Bench Mid Rows », « Donkey Calf Raises »,
    « Dumbbell Curls ». Exiger le singulier exact laissait 319 exercices en
    « à classer » sur les 876 de free-exercise-db, dont la moitié n'étaient
    qu'un « s » de trop — constaté à l'échantillon du 13/09, avant écriture.
    C'est exactement ce que le mode `--sample` existe pour attraper.
    """
    for word in words:
        token = normalize(word).strip()
        if not token:
            continue
        head, _, last = token.rpartition(" ")
        prefix = f"{head} " if head else ""
        for tail in (last, f"{last}s", f"{last}es"):
            if f" {prefix}{tail} " in haystack:
                return True
    return False


@dataclass(frozen=True)
class Taxonomy:
    """Ce qu'on a pu dire d'un exercice. `UNCLASSIFIED` quand on n'a rien dit."""

    group: str
    pattern: str
    equipment: str
    difficulty: int
    effort: str
    unilateral: bool

    @property
    def classified(self) -> bool:
        """Assez rangé pour servir le générateur ?

        Le groupe **et** le pattern : sans groupe on ne sait pas quoi
        travailler, sans pattern on ne sait pas varier. Le matériel inconnu,
        lui, se contourne — on le traite comme une contrainte non satisfaite.
        """
        return self.group != UNCLASSIFIED and self.pattern != UNCLASSIFIED


def classify(
    name: str,
    *,
    hints: Iterable[str] = (),
    equipment_hint: Optional[str] = None,
    level_hint: Optional[str] = None,
) -> Taxonomy:
    """Range un exercice depuis son nom et ce que la base d'origine en dit.

    Les indices sont concaténés au nom : la base dit « stretching » dans un
    champ et « abs » dans un autre, et aucun des deux n'est fiable seul.

    **Ce qui n'est pas reconnu reste `UNCLASSIFIED`.** Un exercice à classer est
    inutile au générateur ; un exercice mal classé lui fait proposer un soulevé
    de terre en séance de mobilité, ce qui est bien pire.
    """
    haystack = normalize(" ".join([name, *hints]))
    name_only = normalize(name)

    group = UNCLASSIFIED
    for candidate, words in GROUP_WORDS.items():
        if _hit(haystack, words):
            group = candidate
            break

    pattern = UNCLASSIFIED
    for candidate, words in PATTERN_WORDS:
        if _hit(haystack, words):
            pattern = candidate
            break

    equipment = UNCLASSIFIED
    sources = [haystack]
    if equipment_hint:
        sources.insert(0, normalize(equipment_hint))
    for candidate, words in EQUIPMENT_WORDS:
        if any(_hit(source, words) for source in sources):
            equipment = candidate
            break

    difficulty = LEVEL_DIFFICULTY.get(
        normalize(level_hint or "").strip(), DEFAULT_DIFFICULTY
    )
    if _hit(name_only, HARDER_WORDS):
        difficulty = min(5, difficulty + 1)
    elif _hit(name_only, EASIER_WORDS):
        difficulty = max(1, difficulty - 1)

    effort = EFFORT_TIME if pattern in TIME_PATTERNS else EFFORT_REPS
    unilateral = _hit(haystack, UNILATERAL_WORDS)

    return Taxonomy(
        group=group,
        pattern=pattern,
        equipment=equipment,
        difficulty=difficulty,
        effort=effort,
        unilateral=unilateral,
    )


# ── Le glossaire français ──────────────────────────────────────────────────
#
# Appliqué **aux motifs**, pas aux phrases : on traduit « Barbell Bench Press »
# en composant « Barre » + « Développé couché », et non en cherchant la chaîne
# entière dans une table. C'est ce qui permet à cent lignes de glossaire de
# couvrir des centaines d'exercices.
#
# Ce qui ne tombe sur **aucun** motif de mouvement garde `name_fr` à NULL :
# traduire à moitié donnerait « Barre Hip Thrust », qui n'est ni anglais ni
# français et qui se lit encore plus mal que l'original.

# Le mouvement — la tête du nom. Sans lui, pas de traduction du tout.
MOVEMENT_FR: tuple[tuple[str, str], ...] = (
    ("bench press", "Développé couché"),
    ("overhead press", "Développé militaire"),
    ("shoulder press", "Développé épaules"),
    ("military press", "Développé militaire"),
    ("incline press", "Développé incliné"),
    ("decline press", "Développé décliné"),
    ("chest press", "Développé poitrine"),
    ("leg press", "Presse à cuisses"),
    ("push press", "Développé avec impulsion"),
    ("push-up", "Pompes"),
    ("pushup", "Pompes"),
    ("push up", "Pompes"),
    ("pull-up", "Tractions"),
    ("pullup", "Tractions"),
    ("pull up", "Tractions"),
    ("chin-up", "Tractions supination"),
    ("chinup", "Tractions supination"),
    ("pulldown", "Tirage vertical"),
    ("pull down", "Tirage vertical"),
    ("face pull", "Tirage à la nuque"),
    ("upright row", "Rowing menton"),
    ("row", "Tirage horizontal"),
    ("shrug", "Haussement d'épaules"),
    ("deadlift", "Soulevé de terre"),
    ("good morning", "Good morning"),
    ("hip thrust", "Hip thrust"),
    ("glute bridge", "Pont fessier"),
    ("hip hinge", "Charnière de hanche"),
    ("kettlebell swing", "Swing kettlebell"),
    ("swing", "Swing"),
    ("split squat", "Fente bulgare"),
    ("squat", "Squat"),
    ("lunge", "Fente"),
    ("step-up", "Montée sur banc"),
    ("step up", "Montée sur banc"),
    ("calf raise", "Extension des mollets"),
    ("leg curl", "Leg curl"),
    ("leg extension", "Leg extension"),
    ("leg raise", "Relevé de jambes"),
    ("knee raise", "Relevé de genoux"),
    ("crunch", "Crunch"),
    ("sit-up", "Redressement assis"),
    ("situp", "Redressement assis"),
    ("sit up", "Redressement assis"),
    ("side plank", "Planche latérale"),
    ("plank", "Gainage"),
    ("hollow hold", "Hollow body"),
    ("hollow body", "Hollow body"),
    ("mountain climber", "Montées de genoux au sol"),
    ("bird dog", "Chien d'arrêt"),
    ("bird-dog", "Chien d'arrêt"),
    ("dead bug", "Dead bug"),
    ("deadbug", "Dead bug"),
    ("pallof press", "Pallof press"),
    ("back extension", "Extension lombaire"),
    ("hyperextension", "Extension lombaire"),
    ("superman", "Superman"),
    ("curl", "Flexion des bras"),
    ("triceps extension", "Extension triceps"),
    ("skullcrusher", "Barre au front"),
    ("kickback", "Extension arrière"),
    ("dip", "Dips"),
    ("dips", "Dips"),
    ("fly", "Écarté"),
    ("flye", "Écarté"),
    ("lateral raise", "Élévation latérale"),
    ("front raise", "Élévation frontale"),
    ("rear delt raise", "Élévation postérieure"),
    ("burpee", "Burpee"),
    ("farmer's walk", "Marche du fermier"),
    ("farmers walk", "Marche du fermier"),
    ("carry", "Portage"),
    ("bear crawl", "Marche de l'ours"),
    ("clean", "Épaulé"),
    ("snatch", "Arraché"),
    ("thruster", "Thruster"),
    ("wall sit", "Chaise"),
    ("stretch", "Étirement"),
    ("cat cow", "Chat-vache"),
    ("cat-cow", "Chat-vache"),
    ("shoulder dislocate", "Passage de bâton"),
    ("arm circle", "Cercles de bras"),
    ("jumping jack", "Jumping jack"),
    ("box jump", "Saut sur boîte"),
    ("turkish get-up", "Relevé turc"),
    ("get-up", "Relevé"),
)

# Le matériel et la position — ce qui vient devant ou derrière.
QUALIFIER_FR: tuple[tuple[str, str], ...] = (
    ("barbell", "à la barre"),
    ("dumbbell", "aux haltères"),
    ("kettlebell", "au kettlebell"),
    ("cable", "à la poulie"),
    ("machine", "à la machine"),
    ("smith machine", "à la Smith machine"),
    ("resistance band", "à l'élastique"),
    ("band", "à l'élastique"),
    ("bodyweight", "au poids du corps"),
    ("body only", "au poids du corps"),
    ("medicine ball", "au medicine ball"),
    ("stability ball", "au ballon"),
    ("swiss ball", "au ballon"),
    ("bosu", "au BOSU"),
    ("ez bar", "à la barre EZ"),
    ("e-z curl bar", "à la barre EZ"),
    ("weighted", "lesté"),
    ("assisted", "assisté"),
    ("one arm", "à un bras"),
    ("one-arm", "à un bras"),
    ("single arm", "à un bras"),
    ("single-arm", "à un bras"),
    ("one leg", "à une jambe"),
    ("one-leg", "à une jambe"),
    ("single leg", "à une jambe"),
    ("single-leg", "à une jambe"),
    ("alternating", "alterné"),
    ("seated", "assis"),
    ("standing", "debout"),
    ("lying", "allongé"),
    ("kneeling", "à genoux"),
    ("incline", "incliné"),
    ("decline", "décliné"),
    ("bulgarian", "bulgare"),
    ("romanian", "roumain"),
    ("close grip", "prise serrée"),
    ("wide grip", "prise large"),
    ("reverse grip", "prise inversée"),
    ("overhead", "au-dessus de la tête"),
    ("front", "devant"),
    ("side", "latéral"),
    ("reverse", "inversé"),
)


def translate_name(name: str) -> Optional[str]:
    """Le nom en français, ou `None` quand on ne sait pas le dire.

    Composé par motifs : « Barbell Bench Press » donne « Développé couché à la
    barre ». Un exercice dont le **mouvement** n'est pas reconnu rend `None` —
    traduire à moitié donnerait « Barre Hip Thrust », qui n'est ni anglais ni
    français et se lit encore plus mal que l'original.

    Rend `None` aussi quand rien n'est à traduire : un nom déjà français
    n'entre pas ici (cf. `needs_translation`).
    """
    haystack = normalize(name)

    # Le motif le plus **spécifique** gagne : d'abord le nombre de mots, la
    # longueur ensuite. Sans quoi « Cat Cow Stretch » tomberait sur
    # « stretch » — plus long que « cat cow » — et perdrait tout ce qui le
    # distingue d'un étirement quelconque.
    movement: Optional[str] = None
    matched = ""
    best = (0, 0)
    for english, french in MOVEMENT_FR:
        token = f" {normalize(english).strip()} "
        if token not in haystack:
            continue
        rank = (len(token.split()), len(token))
        if rank > best:
            movement, matched, best = french, token, rank
    if movement is None:
        return None

    remainder = haystack.replace(matched, " ")
    qualifiers: list[str] = []
    for english, french in QUALIFIER_FR:
        token = f" {normalize(english).strip()} "
        if token not in remainder or french in qualifiers:
            continue
        # « Bulgarian Split Squat » dit déjà « bulgare » dans son mouvement :
        # le répéter donnerait « Fente bulgare bulgare ».
        if normalize(french).strip() in normalize(movement):
            remainder = remainder.replace(token, " ")
            continue
        qualifiers.append(french)
        remainder = remainder.replace(token, " ")

    # Deux qualificatifs au plus. « Développé couché à la barre prise serrée
    # incliné assis » n'est pas un nom, c'est une notice.
    if qualifiers:
        return f"{movement} {' '.join(qualifiers[:2])}"
    return movement


def looks_french(name: str) -> bool:
    """Vrai quand le nom est déjà en français — inutile de le traduire.

    Un accent, une préposition française, ou un mot qu'on a écrit nous-mêmes :
    c'est grossier, et il suffit que ça le reste, parce que la seule
    conséquence d'une erreur est de retraduire un nom déjà bon.
    """
    if any(ch in name for ch in "éèêàùçôîï"):
        return True
    lowered = f" {name.lower()} "
    return any(
        token in lowered
        for token in (
            " au ", " aux ", " de ", " des ", " du ", " à ", " le ", " la ",
            " les ", " sur ", " avec ", " sans ", " une ", " un ",
        )
    )


def french_name(name: str, translations: Optional[dict[str, str]] = None) -> Optional[str]:
    """Le nom français, dans l'ordre de confiance.

    1. La traduction **humaine** de wger, quand la base en a une. Elle est
       écrite par des gens, sous licence libre, et elle vaut toujours mieux
       qu'un glossaire.
    2. Le nom lui-même s'il est déjà français (le catalogue maison).
    3. Le glossaire déterministe.
    4. Rien — et l'exercice n'entrera ni dans une formule ni dans le
       générateur. C'est le but : « Barbell Hip Thrust » au milieu d'une séance
       ne se lit pas à bout de bras.
    """
    if translations:
        for key in ("fr", "fr-fr", "français", "francais"):
            value = translations.get(key)
            if value and value.strip():
                return value.strip()
    if looks_french(name):
        return name
    return translate_name(name)
