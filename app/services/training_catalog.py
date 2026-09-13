"""La bibliothèque d'exercices et les formules — **écrites ici, pas copiées**.

Décidé le 13/09 : les programmes d'entraînement sont composés à partir de bases
**ouvertes** (wger, free-exercise-db), et jamais recopiés depuis un site
commercial. Ce module est la moitié « composée » de cette décision.

Ce qu'il contient et pourquoi :

- **Les consignes sont rédigées pour ce projet**, en français, en une ou deux
  phrases. Elles nous appartiennent. C'est ce qui permet de bâtir des séances
  sans reprendre le texte de personne — et c'est aussi ce qui les rend
  corrigibles : on sait ce qu'on a voulu dire.
- **Les bases ouvertes apportent les images et les groupes musculaires**, par
  `scripts/import_exercises.py`, qui rapproche sur les `aliases` anglais.
  Source et licence restent sur la ligne. Un exercice sans image reste
  parfaitement utilisable : l'image est un confort, pas la donnée.
- **Chaque formule porte le principe qui la justifie**, en une ligne. C'est ce
  qui la distingue d'un programme ramassé ailleurs : on peut la défendre, donc
  la corriger.

Les cinq formules du document design (`docs/DESIGN-EXPLORATION.md` §3) —
Réveil 8 min, Post-surf 12 min, Abdos 15 min, Souplesse longue 25 min, Renfo
surf 28 min — plus deux variantes chacune. Les variantes ne sont pas de la
décoration : une formule faite tous les matins pendant six mois se fait de
moins en moins bien, puis plus du tout.

Le contenu vit dans du code et non dans une migration : il évoluera, et on ne
va pas écrire une migration par correction de tempo.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional

# ── Objectifs ──────────────────────────────────────────────────────────────
#
# Les trois du document design. La **valeur de départ n'est pas ici** : c'est
# la première mesure. Un départ tapé au clavier est une estimation qu'on
# prendra ensuite pour une mesure, et c'est précisément ce qu'on veut éviter.

OBJECTIVES: tuple[dict[str, Any], ...] = (
    {
        "slug": "assouplissement",
        "name": "Assouplissement",
        "measure": (
            "Distance mains-sol, jambes tendues, debout. Négatif au-dessus du "
            "sol, positif quand les mains passent sous la ligne des pieds. "
            "Toujours à froid, jamais après une séance."
        ),
        "unit": "cm",
        "direction": "up",
        "target_value": 0.0,
        "measure_every_days": 21,
        "position": 0,
    },
    {
        "slug": "mobilite-thoracique",
        "name": "Mobilité",
        "measure": (
            "Rotation thoracique, à quatre pattes, main derrière la tête : "
            "angle du coude par rapport au sol, côté le moins souple."
        ),
        "unit": "deg",
        "direction": "up",
        "target_value": 45.0,
        "measure_every_days": 21,
        "position": 1,
    },
    {
        "slug": "gainage",
        "name": "Gainage",
        "measure": (
            "Planche sur les avant-bras, tenue jusqu'à la rupture de "
            "l'alignement — pas jusqu'à l'échec. Une planche cassée ne compte "
            "plus."
        ),
        # En secondes : « 2:10 » est un affichage, comme le 6'2 d'une planche.
        "unit": "s",
        "direction": "up",
        "target_value": 180.0,
        "measure_every_days": 21,
        "position": 2,
    },
)


# ── Exercices ──────────────────────────────────────────────────────────────
#
# `aliases` : les noms anglais sous lesquels l'exercice est connu dans les
# bases ouvertes. C'est la clé de rapprochement de l'import — il enrichit une
# ligne existante au lieu d'en créer une deuxième sous un autre nom.

# ── La taxonomie du catalogue maison, à la main ────────────────────────────
#
# Les 1 661 exercices importés sont classés par règles
# (`services/exercise_taxonomy.py`), avec une relecture d'échantillon avant
# écriture. **Ces trente-là ne le sont pas** : ils sont rédigés ici, un par un,
# et les ranger à la main coûte trente lignes une fois pour toutes.
#
# C'est ce qui fait la différence là où une règle se trompe : la fente basse
# hanche ouverte est de la **mobilité de hanche**, pas un étirement de jambe ;
# la planche avec touche d'épaule est de l'**anti-rotation**, pas du gainage
# statique ; le pop-up est une **poussée**. Aucune de ces trois nuances ne
# s'attrape depuis un nom, et toutes les trois changent ce que le générateur
# propose.
#
# `(groupe, pattern, matériel, difficulté, temps-ou-reps, unilatéral)`.
BUILTIN_TAXONOMY: dict[str, tuple[str, str, str, int, str, bool]] = {
    # Mobilité
    "chat-vache": ("dos", "mobilite", "aucun", 1, "temps", False),
    "rotation-thoracique": ("dos", "mobilite", "aucun", 2, "temps", True),
    "fente-hanche": ("hanches", "mobilite", "aucun", 2, "temps", True),
    "chien-tete-en-bas": ("dos", "mobilite", "aucun", 2, "temps", False),
    "flexion-avant": ("jambes", "etirement", "aucun", 2, "temps", False),
    "cercles-epaules": ("epaules", "mobilite", "aucun", 1, "temps", False),
    "dislocation-batons": ("epaules", "mobilite", "aucun", 2, "reps", False),
    "pigeon": ("hanches", "etirement", "aucun", 3, "temps", True),
    "etirement-mollets": ("jambes", "etirement", "aucun", 1, "temps", True),
    "cobra": ("dos", "mobilite", "aucun", 2, "temps", False),
    "torsion-au-sol": ("dos", "mobilite", "aucun", 1, "temps", True),
    "accroupi-profond": ("hanches", "mobilite", "aucun", 3, "temps", False),
    # Gainage
    "planche": ("abdos", "gainage-statique", "aucun", 2, "temps", False),
    "planche-laterale": ("abdos", "gainage-statique", "aucun", 3, "temps", True),
    "hollow-body": ("abdos", "gainage-statique", "aucun", 3, "temps", False),
    "dead-bug": ("abdos", "anti-rotation", "aucun", 2, "reps", True),
    "bird-dog": ("abdos", "anti-rotation", "aucun", 2, "reps", True),
    "releve-jambes": ("abdos", "flexion", "aucun", 3, "reps", False),
    "pallof": ("abdos", "anti-rotation", "elastique", 3, "reps", True),
    "gainage-dynamique": ("abdos", "anti-rotation", "aucun", 3, "reps", True),
    # Renforcement
    "pompes": ("poitrine", "poussee", "aucun", 3, "reps", False),
    "pop-up": ("corps-entier", "poussee", "aucun", 3, "reps", False),
    "rotateurs-elastique": ("epaules", "tirage", "elastique", 2, "reps", True),
    "ytw-elastique": ("epaules", "tirage", "elastique", 2, "reps", False),
    "rowing-elastique": ("dos", "tirage", "elastique", 2, "reps", False),
    "squat": ("jambes", "squat", "aucun", 2, "reps", False),
    "fente-avant": ("jambes", "fente", "aucun", 3, "reps", True),
    "pont-fessier": ("hanches", "charniere", "aucun", 2, "reps", False),
    "souleve-terre-une-jambe": ("hanches", "charniere", "aucun", 4, "reps", True),
    "superman": ("dos", "extension", "aucun", 2, "temps", False),
}


EXERCISES: tuple[dict[str, Any], ...] = (
    # ── Mobilité ───────────────────────────────────────────────────────────
    {
        "slug": "chat-vache",
        "name": "Chat-vache",
        "category": "mobility",
        "muscle_group": "dos",
        "instructions": (
            "À quatre pattes, mains sous les épaules. Enroule le dos vers le "
            "plafond en soufflant, puis creuse-le en inspirant. Le mouvement "
            "part du bassin, pas de la nuque."
        ),
        # « Cat Stretch » est le nom sous lequel free-exercise-db le range —
        # vérifié dans le catalogue importé, pas supposé.
        "aliases": ["cat cow", "cat-cow stretch", "cat stretch"],
    },
    {
        "slug": "rotation-thoracique",
        "name": "Rotation thoracique",
        "category": "mobility",
        "muscle_group": "dos",
        "instructions": (
            "À quatre pattes, une main derrière la tête. Ouvre le coude vers "
            "le plafond en suivant du regard, reviens sous le corps. Le "
            "bassin ne bouge pas — c'est ce qui fait que la rotation vient du "
            "thorax."
        ),
        "aliases": ["thoracic rotation", "thread the needle"],
    },
    {
        "slug": "fente-hanche",
        "name": "Fente basse, hanche ouverte",
        "category": "mobility",
        "muscle_group": "hanches",
        "instructions": (
            "Grande fente, genou arrière au sol. Pousse le bassin vers "
            "l'avant sans cambrer, fesse arrière serrée. C'est le psoas qu'on "
            "cherche, et il ne s'étire qu'avec le bassin en rétroversion."
        ),
        "aliases": ["low lunge", "hip flexor stretch", "couch stretch"],
    },
    {
        "slug": "chien-tete-en-bas",
        "name": "Chien tête en bas",
        "category": "mobility",
        "muscle_group": "chaîne postérieure",
        "instructions": (
            "En V inversé, talons vers le sol, dos long. Plie les genoux "
            "autant qu'il faut pour garder le dos droit : c'est le dos qui "
            "compte, pas les talons."
        ),
        "aliases": ["downward dog", "downward facing dog"],
    },
    {
        "slug": "flexion-avant",
        "name": "Flexion avant, jambes tendues",
        "category": "mobility",
        "muscle_group": "ischio-jambiers",
        "instructions": (
            "Debout, pieds joints, descends les mains vers le sol sans "
            "plier. Relâche la nuque. C'est la mesure de l'objectif "
            "assouplissement — fais-la toujours de la même façon."
        ),
        "aliases": ["standing forward bend", "toe touch", "forward fold"],
    },
    {
        "slug": "cercles-epaules",
        "name": "Cercles d'épaules, bras tendus",
        "category": "mobility",
        "muscle_group": "épaules",
        "instructions": (
            "Bras tendus sur les côtés, dessine des cercles de plus en plus "
            "grands, dans un sens puis dans l'autre. Sans hausser les "
            "épaules : si elles montent, les cercles sont trop grands."
        ),
        "aliases": ["arm circles", "shoulder circles"],
    },
    {
        "slug": "dislocation-batons",
        "name": "Passage de bâton",
        "category": "mobility",
        "muscle_group": "épaules",
        "instructions": (
            "Un bâton ou une serviette tendue devant, mains très écartées. "
            "Passe les bras au-dessus de la tête jusque derrière le dos, "
            "coudes tendus. Rapproche les mains au fil des semaines."
        ),
        "aliases": ["shoulder dislocate", "shoulder pass through"],
    },
    {
        "slug": "pigeon",
        "name": "Pigeon",
        "category": "mobility",
        "muscle_group": "hanches",
        "instructions": (
            "Tibia avant posé au sol, jambe arrière tendue, buste descendu. "
            "Les hanches restent parallèles — sinon on étire le genou et pas "
            "la hanche."
        ),
        "aliases": ["pigeon pose", "figure four stretch"],
    },
    {
        "slug": "etirement-mollets",
        "name": "Étirement des mollets au mur",
        "category": "mobility",
        "muscle_group": "mollets",
        "instructions": (
            "Avant-pied contre un mur, talon au sol, avance le genou. Tenir "
            "sans rebondir. Un mollet raide ferme la cheville, et une cheville "
            "fermée sort du pop-up en retard."
        ),
        "aliases": ["calf stretch", "wall calf stretch"],
    },
    {
        "slug": "cobra",
        "name": "Cobra",
        "category": "mobility",
        "muscle_group": "dos",
        "instructions": (
            "À plat ventre, mains sous les épaules, monte le buste en "
            "poussant doucement. Épaules basses, fesses relâchées. C'est "
            "l'antidote direct d'une heure de rame."
        ),
        "aliases": ["cobra pose", "cobra stretch"],
    },
    {
        "slug": "torsion-au-sol",
        "name": "Torsion allongée",
        "category": "mobility",
        "muscle_group": "dos",
        "instructions": (
            "Sur le dos, un genou ramené puis emmené de l'autre côté, bras en "
            "croix. Les deux épaules restent au sol : elles décident de "
            "l'amplitude, pas le genou."
        ),
        "aliases": ["supine twist", "lying spinal twist"],
    },
    {
        "slug": "accroupi-profond",
        "name": "Accroupi profond",
        "category": "mobility",
        "muscle_group": "hanches",
        "instructions": (
            "Pieds à plat, descends le plus bas possible, coudes à "
            "l'intérieur des genoux. Talons au sol si tu peux, sur une cale "
            "sinon — mais pas sur la pointe des pieds."
        ),
        "aliases": ["deep squat hold", "malasana", "third world squat"],
    },
    # ── Gainage ────────────────────────────────────────────────────────────
    {
        "slug": "planche",
        "name": "Planche",
        "category": "core",
        "muscle_group": "ceinture abdominale",
        "instructions": (
            "Sur les avant-bras, corps en ligne, fesses serrées, bassin en "
            "rétroversion. Dès que le bas du dos creuse, la série est finie — "
            "même si tu peux « tenir » encore."
        ),
        "aliases": ["plank", "front plank", "forearm plank"],
    },
    {
        "slug": "planche-laterale",
        "name": "Planche latérale",
        "category": "core",
        "muscle_group": "obliques",
        "instructions": (
            "Sur un avant-bras, corps aligné vu de face, hanche haute. C'est "
            "elle qui tient la rame de côté quand la vague pousse."
        ),
        "aliases": ["side plank"],
    },
    {
        "slug": "hollow-body",
        "name": "Hollow body",
        "category": "core",
        "muscle_group": "ceinture abdominale",
        "instructions": (
            "Sur le dos, bas du dos plaqué au sol, jambes et épaules "
            "décollées. Descends les jambes jusqu'à la limite où le dos reste "
            "plaqué, pas plus bas."
        ),
        "aliases": ["hollow hold", "hollow body hold"],
    },
    {
        "slug": "dead-bug",
        "name": "Dead bug",
        "category": "core",
        "muscle_group": "ceinture abdominale",
        "instructions": (
            "Sur le dos, bras et genoux au plafond. Descends un bras et la "
            "jambe opposée, sans que le dos décolle. Lentement : c'est le "
            "contrôle qu'on travaille, pas le nombre."
        ),
        "aliases": ["dead bug", "deadbug"],
    },
    {
        "slug": "bird-dog",
        "name": "Bird dog",
        "category": "core",
        "muscle_group": "dos",
        "instructions": (
            "À quatre pattes, tends le bras et la jambe opposée à "
            "l'horizontale. Le bassin ne tourne pas — pose un verre sur le "
            "bas du dos, en imagination, et ne le renverse pas."
        ),
        "aliases": ["bird dog", "quadruped opposite arm leg raise"],
    },
    {
        "slug": "releve-jambes",
        "name": "Relevés de jambes tendues",
        "category": "core",
        "muscle_group": "ceinture abdominale",
        "instructions": (
            "Sur le dos, mains sous les fesses, jambes tendues. Monte et "
            "descends sans toucher le sol, dos toujours plaqué."
        ),
        "aliases": ["leg raise", "lying leg raise"],
    },
    {
        "slug": "pallof",
        "name": "Pallof press à l'élastique",
        "category": "core",
        "muscle_group": "obliques",
        "instructions": (
            "Élastique fixé de côté à hauteur de poitrine, tends les bras "
            "devant toi sans laisser le buste tourner. L'anti-rotation est ce "
            "qui manque le plus aux surfeurs."
        ),
        "aliases": ["pallof press", "anti rotation press"],
    },
    # ── Renfo ──────────────────────────────────────────────────────────────
    {
        "slug": "pompes",
        "name": "Pompes",
        "category": "strength",
        "muscle_group": "pectoraux",
        "instructions": (
            "Mains sous les épaules, corps gainé, coudes à 45°. Descends la "
            "poitrine au sol. C'est le geste du pop-up, exactement."
        ),
        "aliases": ["push up", "push-ups", "pushups"],
    },
    {
        "slug": "pop-up",
        "name": "Pop-up à sec",
        "category": "strength",
        "muscle_group": "corps entier",
        "instructions": (
            "Allongé comme sur la planche, une pompe explosive puis les pieds "
            "passent sous le corps d'un coup, en position de surf. Regarde "
            "devant, pas tes pieds."
        ),
        "aliases": ["burpee", "pop up"],
    },
    {
        "slug": "rotateurs-elastique",
        "name": "Rotations externes à l'élastique",
        "category": "strength",
        "muscle_group": "coiffe des rotateurs",
        "instructions": (
            "Coude au corps plié à 90°, élastique devant, ouvre l'avant-bras "
            "vers l'extérieur. Lentement, sans décoller le coude. C'est la "
            "seule chose qui protège l'épaule d'une saison de rame."
        ),
        "aliases": ["external rotation", "band external rotation"],
    },
    {
        "slug": "ytw-elastique",
        "name": "Y-T-W à plat ventre",
        "category": "strength",
        "muscle_group": "épaules",
        "instructions": (
            "À plat ventre, bras au sol. Décolle-les en dessinant un Y, puis "
            "un T, puis un W. Le cou reste long, les omoplates descendent."
        ),
        "aliases": ["ytw raise", "prone y raise", "prone t raise"],
    },
    {
        "slug": "rowing-elastique",
        "name": "Tirage horizontal à l'élastique",
        "category": "strength",
        "muscle_group": "dos",
        "instructions": (
            "Élastique devant, tire les coudes vers l'arrière en serrant les "
            "omoplates. Le dos équilibre tout ce que la rame fait aux "
            "épaules vers l'avant."
        ),
        "aliases": ["band row", "seated row", "resistance band row"],
    },
    {
        "slug": "squat",
        "name": "Squat au poids du corps",
        "category": "strength",
        "muscle_group": "jambes",
        "instructions": (
            "Pieds largeur d'épaules, descends jusqu'aux cuisses parallèles "
            "au moins, dos droit, talons au sol."
        ),
        "aliases": ["bodyweight squat", "air squat", "squat"],
    },
    {
        "slug": "fente-avant",
        "name": "Fentes avant alternées",
        "category": "strength",
        "muscle_group": "jambes",
        "instructions": (
            "Un grand pas en avant, genou arrière vers le sol, buste droit. "
            "Remonte en poussant sur le talon avant."
        ),
        "aliases": ["forward lunge", "lunge", "alternating lunge"],
    },
    {
        "slug": "pont-fessier",
        "name": "Pont fessier",
        "category": "strength",
        "muscle_group": "fessiers",
        "instructions": (
            "Sur le dos, pieds au sol, monte le bassin en serrant les fesses. "
            "Pas de cambrure : c'est le fessier qui monte le bassin, pas le "
            "bas du dos."
        ),
        "aliases": ["glute bridge", "hip bridge"],
    },
    {
        "slug": "souleve-terre-une-jambe",
        "name": "Soulevé de terre à une jambe",
        "category": "strength",
        "muscle_group": "chaîne postérieure",
        "instructions": (
            "En équilibre sur une jambe, penche le buste en tendant l'autre "
            "jambe derrière. Dos droit, hanches parallèles. L'équilibre fait "
            "partie de l'exercice."
        ),
        "aliases": ["single leg deadlift", "single-leg romanian deadlift"],
    },
    {
        "slug": "superman",
        "name": "Superman",
        "category": "strength",
        "muscle_group": "lombaires",
        "instructions": (
            "À plat ventre, décolle bras et jambes. Tenir sans à-coups. "
            "C'est la position de rame, et elle se travaille à sec."
        ),
        "aliases": ["superman", "superman hold"],
    },
    {
        "slug": "gainage-dynamique",
        "name": "Planche avec touche d'épaule",
        "category": "core",
        "muscle_group": "ceinture abdominale",
        "instructions": (
            "En position de pompe, touche l'épaule opposée d'une main sans "
            "que le bassin bouge. Écarte les pieds si ça balance."
        ),
        "aliases": ["plank shoulder tap", "shoulder taps"],
    },
)


# ── Formules ───────────────────────────────────────────────────────────────
#
# Chaque entrée : `items` = (slug d'exercice, séries, reps, durée_s, repos_s,
# note). `reps` **ou** `duration_s`, jamais les deux — un gainage se tient, une
# rotation se compte.

def _item(
    exercise: str,
    sets: int = 1,
    reps: Optional[int] = None,
    duration_s: Optional[int] = None,
    rest_s: int = 0,
    note: Optional[str] = None,
    tempo: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "exercise": exercise,
        "sets": sets,
        "reps": reps,
        "duration_s": duration_s,
        "rest_s": rest_s,
        "note": note,
        "tempo": tempo,
    }


FORMULAS: tuple[dict[str, Any], ...] = (
    # ── Réveil, 8 min, tous les matins ────────────────────────────────────
    {
        "slug": "reveil",
        "name": "Réveil",
        "duration_min": 8,
        "weekly_target": 7,
        "principle": (
            "Ouvrir la colonne et les hanches avant que la journée les "
            "referme — huit minutes tenables tous les jours valent mieux "
            "qu'une heure tenue deux fois."
        ),
        "objective_slugs": ["mobilite-thoracique", "assouplissement"],
        "tags": ["morning", "mobility"],
        "position": 0,
        "items": [
            _item("chat-vache", sets=1, reps=10),
            _item("rotation-thoracique", sets=1, reps=8, note="par côté"),
            _item("fente-hanche", sets=1, duration_s=40, note="par côté"),
            _item("chien-tete-en-bas", sets=1, duration_s=45),
            _item("flexion-avant", sets=1, duration_s=40),
            _item("cercles-epaules", sets=1, reps=12, note="dans les deux sens"),
        ],
    },
    {
        "slug": "reveil-dos",
        "name": "Réveil — dos",
        "duration_min": 8,
        "weekly_target": 0,
        "principle": (
            "La même durée, centrée sur la colonne : pour les matins où le "
            "bas du dos est raide après une grosse session."
        ),
        "objective_slugs": ["mobilite-thoracique"],
        "tags": ["morning", "mobility"],
        "variant_of": "reveil",
        "position": 1,
        "items": [
            _item("chat-vache", sets=1, reps=12),
            _item("cobra", sets=1, duration_s=40),
            _item("torsion-au-sol", sets=1, duration_s=45, note="par côté"),
            _item("bird-dog", sets=1, reps=8, note="par côté"),
            _item("chien-tete-en-bas", sets=1, duration_s=45),
        ],
    },
    {
        "slug": "reveil-hanches",
        "name": "Réveil — hanches",
        "duration_min": 8,
        "weekly_target": 0,
        "principle": (
            "Hanches et chevilles, les deux articulations qui décident de la "
            "hauteur du pop-up. À faire les matins de session."
        ),
        "objective_slugs": ["assouplissement"],
        "tags": ["morning", "mobility"],
        "variant_of": "reveil",
        "position": 2,
        "items": [
            _item("accroupi-profond", sets=1, duration_s=60),
            _item("fente-hanche", sets=1, duration_s=45, note="par côté"),
            _item("pigeon", sets=1, duration_s=45, note="par côté"),
            _item("etirement-mollets", sets=1, duration_s=40, note="par côté"),
        ],
    },
    # ── Post-surf, 12 min, après chaque session ───────────────────────────
    {
        "slug": "post-surf",
        "name": "Post-surf",
        "duration_min": 12,
        "weekly_target": 0,
        "principle": (
            "Rendre aux épaules et aux hanches ce qu'une heure de rame leur a "
            "pris. À chaud, dans l'heure qui suit — c'est le seul moment où "
            "l'amplitude gagnée reste."
        ),
        "objective_slugs": ["mobilite-thoracique", "assouplissement"],
        "tags": ["post_surf", "mobility"],
        "position": 3,
        "items": [
            _item("cobra", sets=1, duration_s=45),
            _item("dislocation-batons", sets=1, reps=10),
            _item("rotation-thoracique", sets=1, reps=8, note="par côté"),
            _item("pigeon", sets=1, duration_s=60, note="par côté"),
            _item("fente-hanche", sets=1, duration_s=45, note="par côté"),
            _item("flexion-avant", sets=1, duration_s=45),
            _item("torsion-au-sol", sets=1, duration_s=45, note="par côté"),
        ],
    },
    {
        "slug": "post-surf-epaules",
        "name": "Post-surf — épaules",
        "duration_min": 12,
        "weekly_target": 0,
        "principle": (
            "Après une session de rame longue ou de gros : tout sur la "
            "coiffe et l'ouverture de poitrine, rien sur les jambes."
        ),
        "objective_slugs": ["mobilite-thoracique"],
        "tags": ["post_surf", "mobility"],
        "variant_of": "post-surf",
        "position": 4,
        "items": [
            _item("dislocation-batons", sets=2, reps=10, rest_s=20),
            _item("cercles-epaules", sets=1, reps=15),
            _item("cobra", sets=1, duration_s=45),
            _item("rotateurs-elastique", sets=2, reps=12, rest_s=30, note="par bras"),
            _item("ytw-elastique", sets=1, reps=8, note="Y, puis T, puis W"),
        ],
    },
    {
        "slug": "post-surf-court",
        "name": "Post-surf — express",
        "duration_min": 6,
        "weekly_target": 0,
        "principle": (
            "Six minutes sur le parking, en combinaison. Une version courte "
            "faite vaut infiniment mieux qu'une version longue reportée."
        ),
        "objective_slugs": ["mobilite-thoracique"],
        "tags": ["post_surf", "mobility"],
        "variant_of": "post-surf",
        "position": 5,
        "items": [
            _item("dislocation-batons", sets=1, reps=10),
            _item("cobra", sets=1, duration_s=40),
            _item("fente-hanche", sets=1, duration_s=40, note="par côté"),
            _item("flexion-avant", sets=1, duration_s=40),
        ],
    },
    # ── Abdos, 15 min, 3 × / semaine ──────────────────────────────────────
    {
        "slug": "abdos",
        "name": "Abdos",
        "duration_min": 15,
        "weekly_target": 3,
        "principle": (
            "Du gainage tenu et de l'anti-rotation, pas des crunchs : ce "
            "qu'on cherche est de tenir la planche droite sous la poussée, "
            "pas de plier le tronc."
        ),
        "objective_slugs": ["gainage"],
        "tags": ["core"],
        "position": 6,
        "items": [
            _item("planche", sets=3, duration_s=45, rest_s=30),
            _item("planche-laterale", sets=2, duration_s=35, rest_s=25, note="par côté"),
            _item("dead-bug", sets=3, reps=10, rest_s=30, note="par côté"),
            _item("hollow-body", sets=3, duration_s=30, rest_s=30),
            _item("bird-dog", sets=2, reps=10, rest_s=25, note="par côté"),
        ],
    },
    {
        "slug": "abdos-dynamique",
        "name": "Abdos — dynamique",
        "duration_min": 15,
        "weekly_target": 0,
        "principle": (
            "Même durée, en mouvement : le gainage statique progresse vite et "
            "plafonne. Le bassin qui ne bouge pas pendant que les membres "
            "bougent est le vrai test."
        ),
        "objective_slugs": ["gainage"],
        "tags": ["core"],
        "variant_of": "abdos",
        "position": 7,
        "items": [
            _item("gainage-dynamique", sets=3, reps=16, rest_s=30, note="8 par côté"),
            _item("dead-bug", sets=3, reps=12, rest_s=30, note="par côté"),
            _item("releve-jambes", sets=3, reps=12, rest_s=30),
            _item("planche-laterale", sets=2, duration_s=40, rest_s=25, note="par côté"),
        ],
    },
    {
        "slug": "abdos-anti-rotation",
        "name": "Abdos — anti-rotation",
        "duration_min": 15,
        "weekly_target": 0,
        "principle": (
            "Tout sur l'anti-rotation à l'élastique. C'est ce qui manque le "
            "plus aux surfeurs, et ça ne se travaille pas en planche."
        ),
        "objective_slugs": ["gainage"],
        "tags": ["core"],
        "variant_of": "abdos",
        "position": 8,
        "items": [
            _item("pallof", sets=3, reps=10, rest_s=40, note="par côté, lentement"),
            _item("planche-laterale", sets=3, duration_s=40, rest_s=30, note="par côté"),
            _item("bird-dog", sets=3, reps=10, rest_s=30, note="par côté"),
            _item("planche", sets=2, duration_s=60, rest_s=40),
        ],
    },
    # ── Souplesse longue, 25 min, 2 × / semaine ───────────────────────────
    {
        "slug": "souplesse-longue",
        "name": "Souplesse longue",
        "duration_min": 25,
        "weekly_target": 2,
        "principle": (
            "Des postures tenues longtemps — une à deux minutes : c'est la "
            "durée, pas l'intensité, qui gagne de l'amplitude durable. Rien "
            "ne doit tirer au point de couper la respiration."
        ),
        "objective_slugs": ["assouplissement", "mobilite-thoracique"],
        "tags": ["mobility"],
        "position": 9,
        "items": [
            _item("chat-vache", sets=1, reps=12),
            _item("chien-tete-en-bas", sets=1, duration_s=90),
            _item("flexion-avant", sets=3, duration_s=75, rest_s=20),
            _item("pigeon", sets=2, duration_s=90, rest_s=20, note="par côté"),
            _item("fente-hanche", sets=2, duration_s=75, rest_s=20, note="par côté"),
            _item("accroupi-profond", sets=2, duration_s=90, rest_s=30),
            _item("etirement-mollets", sets=2, duration_s=60, rest_s=15, note="par côté"),
            _item("torsion-au-sol", sets=1, duration_s=90, note="par côté"),
        ],
    },
    {
        "slug": "souplesse-ischios",
        "name": "Souplesse — ischios",
        "duration_min": 22,
        "weekly_target": 0,
        "principle": (
            "Centrée sur la chaîne postérieure, qui est ce qui tient la "
            "mesure mains-sol. À faire quand l'objectif assouplissement "
            "stagne."
        ),
        "objective_slugs": ["assouplissement"],
        "tags": ["mobility"],
        "variant_of": "souplesse-longue",
        "position": 10,
        "items": [
            _item("chien-tete-en-bas", sets=2, duration_s=75, rest_s=20),
            _item("flexion-avant", sets=4, duration_s=75, rest_s=25),
            _item("souleve-terre-une-jambe", sets=2, reps=8, rest_s=30, note="par côté, sans charge"),
            _item("etirement-mollets", sets=3, duration_s=60, rest_s=15, note="par côté"),
            _item("pigeon", sets=2, duration_s=75, rest_s=20, note="par côté"),
        ],
    },
    {
        "slug": "souplesse-haut-du-corps",
        "name": "Souplesse — haut du corps",
        "duration_min": 20,
        "weekly_target": 0,
        "principle": (
            "Épaules, poitrine et thorax. La rotation thoracique se gagne "
            "surtout en ouvrant ce qui la bloque devant."
        ),
        "objective_slugs": ["mobilite-thoracique"],
        "tags": ["mobility"],
        "variant_of": "souplesse-longue",
        "position": 11,
        "items": [
            _item("dislocation-batons", sets=3, reps=10, rest_s=25),
            _item("cobra", sets=3, duration_s=60, rest_s=25),
            _item("rotation-thoracique", sets=3, reps=10, rest_s=20, note="par côté"),
            _item("torsion-au-sol", sets=2, duration_s=90, rest_s=20, note="par côté"),
            _item("cercles-epaules", sets=2, reps=15, rest_s=20),
        ],
    },
    # ── Renfo surf, 28 min, 2 × / semaine ─────────────────────────────────
    {
        "slug": "renfo-surf",
        "name": "Renfo surf",
        "duration_min": 28,
        "weekly_target": 2,
        "principle": (
            "Épaules et dos pour tenir la rame, jambes et gainage pour tenir "
            "la planche. Le volume est modeste et le repos court : c'est de "
            "l'endurance de force, pas de la musculation."
        ),
        "objective_slugs": ["gainage"],
        "tags": ["strength"],
        "position": 12,
        "items": [
            _item("pop-up", sets=3, reps=8, rest_s=45),
            _item("pompes", sets=3, reps=12, rest_s=45, tempo="2-0-1"),
            _item("rowing-elastique", sets=3, reps=15, rest_s=45),
            _item("rotateurs-elastique", sets=3, reps=12, rest_s=30, note="par bras"),
            _item("squat", sets=3, reps=15, rest_s=45),
            _item("fente-avant", sets=2, reps=10, rest_s=45, note="par jambe"),
            _item("superman", sets=3, duration_s=30, rest_s=30),
            _item("planche", sets=2, duration_s=45, rest_s=30),
        ],
    },
    {
        "slug": "renfo-epaules",
        "name": "Renfo — épaules et rame",
        "duration_min": 25,
        "weekly_target": 0,
        "principle": (
            "Le haut du corps seul, pour une semaine où les jambes ont déjà "
            "pris cher à l'eau. La coiffe des rotateurs passe avant le reste : "
            "c'est elle qui lâche en premier sur une saison."
        ),
        "objective_slugs": [],
        "tags": ["strength"],
        "variant_of": "renfo-surf",
        "position": 13,
        "items": [
            _item("rotateurs-elastique", sets=4, reps=12, rest_s=30, note="par bras"),
            _item("ytw-elastique", sets=3, reps=8, rest_s=40, note="Y, puis T, puis W"),
            _item("rowing-elastique", sets=4, reps=15, rest_s=40),
            _item("pompes", sets=3, reps=12, rest_s=45, tempo="2-0-1"),
            _item("superman", sets=3, duration_s=35, rest_s=30),
            _item("gainage-dynamique", sets=2, reps=16, rest_s=30, note="8 par côté"),
        ],
    },
    {
        "slug": "renfo-jambes",
        "name": "Renfo — jambes et pop-up",
        "duration_min": 26,
        "weekly_target": 0,
        "principle": (
            "Jambes, fessiers et explosivité du pop-up. À placer les semaines "
            "sans houle, jamais la veille d'une grosse journée."
        ),
        "objective_slugs": [],
        "tags": ["strength"],
        "variant_of": "renfo-surf",
        "position": 14,
        "items": [
            _item("pop-up", sets=4, reps=8, rest_s=50),
            _item("squat", sets=4, reps=15, rest_s=45),
            _item("fente-avant", sets=3, reps=10, rest_s=45, note="par jambe"),
            _item("pont-fessier", sets=3, reps=15, rest_s=35),
            _item("souleve-terre-une-jambe", sets=3, reps=10, rest_s=40, note="par jambe"),
            _item("planche-laterale", sets=2, duration_s=40, rest_s=25, note="par côté"),
        ],
    },
)


def normalize_name(name: str) -> str:
    """Minuscules, sans accent ni ponctuation — la clé de dédoublonnage.

    Sert l'import (`scripts/import_exercises.py`) : « Pompes » et « push-ups »
    ne se ressemblent pas, mais « push up » et « Push-Ups » si, et c'est ce
    qu'il faut éviter d'insérer deux fois.
    """
    folded = unicodedata.normalize("NFKD", name.strip().lower())
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(
        "".join(char if char.isalnum() else " " for char in stripped).split()
    )
