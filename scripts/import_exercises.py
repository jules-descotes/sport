"""Import d'exercices depuis des bases **ouvertes**, et elles seules.

Deux sources, décidées le 13/09 :

- **wger** — `wger.de/api/v2/`, API publique, sans clé. Exercices, muscles,
  images. Licence CC BY-SA 4.0 (contenu contribué).
- **free-exercise-db** — JSON du domaine public sur GitHub, ~870 exercices
  avec images.

**Aucun scraping d'un site commercial de programmes.** C'est contraire aux
CGU, ça casse au premier changement de page, et c'est la même leçon que
`sport=surfing` d'OSM : on vérifie la donnée avant de s'y fier. D'où le mode
`--sample`, qui montre un échantillon et **n'écrit rien** — à passer avant
tout import complet, pour lire de ses yeux ce que les catégories valent.

Ce que l'import fait, et ce qu'il ne fait pas :

- il **enrichit** les exercices rédigés dans `training_catalog.py` (image,
  groupe musculaire, source et licence) en les rapprochant par leurs `aliases`
  anglais. Il ne touche **jamais** aux consignes françaises, qui sont à nous ;
- il **ajoute** le reste de la base comme bibliothèque consultable, source et
  licence sur chaque ligne ;
- il dédoublonne sur le **nom normalisé** — « Push-Ups » et « push up » sont le
  même exercice ;
- il ne supprime rien. Une base ouverte qui perd une entrée ne doit pas vider
  une formule.

Usage :

    python -m scripts.import_exercises --sample            # ne écrit rien
    python -m scripts.import_exercises --source free       # une seule source
    python -m scripts.import_exercises --dry-run
    python -m scripts.import_exercises
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import httpx
from sqlalchemy import select

from app.db.database import async_session
from app.models import load_all_models
from app.models.exercise import Exercise
from app.services.exercise_taxonomy import (
    EQUIPMENT_LABELS,
    GROUP_LABELS,
    PATTERN_LABELS,
    Taxonomy,
    UNCLASSIFIED,
    classify as classify_taxonomy,
    french_name,
)
from app.services.training_catalog import normalize_name

# Tous les modèles, pas seulement ceux dont ce script parle : SQLAlchemy
# résout les relations écrites en chaîne à la configuration des mappers, et
# un module manquant ne se voit qu'à la première requête (panne du 15/09).
load_all_models()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("import_exercises")

FREE_EXERCISE_DB_URL = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/"
    "exercises.json"
)
FREE_EXERCISE_IMAGE_BASE = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
)

WGER_BASE = "https://wger.de/api/v2"
# Anglais : c'est la langue où la base est la plus complète, et c'est aussi
# celle de nos `aliases`. Les consignes françaises sont les nôtres de toute
# façon.
WGER_ENGLISH = 2
# Le français. wger est traduit par des bénévoles, sous licence libre : quand
# la traduction existe, elle vaut mieux que n'importe quel glossaire.
WGER_FRENCH = 12

TIMEOUT_S = 30.0


@dataclass
class Incoming:
    """Un exercice tel qu'une base ouverte le rend, avant écriture."""

    name: str
    category: str
    muscle_group: Optional[str]
    instructions: Optional[str]
    image_url: Optional[str]
    source: str
    license: str
    source_url: Optional[str] = None
    external_id: Optional[str] = None

    # ── Ce que le 13/09 a ajouté ───────────────────────────────────────────
    #
    # `name_fr` vient d'abord des **traductions humaines** de wger, puis d'un
    # glossaire déterministe. Vide quand on n'a pas su le dire : un exercice
    # sans nom français n'entre ni dans une formule ni dans le générateur, et
    # semer une traduction approximative vaudrait moins que ne rien dire.
    name_fr: Optional[str] = None
    description_fr: Optional[str] = None
    # Toutes les images. free-exercise-db en donne deux, et c'est leur
    # alternance qui montre le mouvement.
    images: list[str] = field(default_factory=list)
    # La taxonomie, posée par `services/exercise_taxonomy.py`. Ce qui n'est pas
    # reconnu reste `a-classer` — jamais deviné.
    taxonomy: Optional[Taxonomy] = None

    @property
    def normalized(self) -> str:
        return normalize_name(self.name)


@dataclass
class Report:
    enriched: int = 0
    created: int = 0
    skipped: int = 0
    samples: list[Incoming] = field(default_factory=list)


# ── Catégorisation ─────────────────────────────────────────────────────────
#
# Trois catégories, et trois seulement : `mobility`, `strength`, `core`. Une
# taxonomie fine se vérifie mal, et l'import en apporterait une fausse — c'est
# exactement l'erreur de `sport=surfing`, où une étiquette plausible désignait
# tout autre chose. Ici on classe grossièrement et **on le sait**.

_CORE_WORDS = (
    "abdominal",
    "abs",
    "core",
    "plank",
    "oblique",
    "crunch",
    "hollow",
    "waist",
)
_MOBILITY_WORDS = (
    "stretch",
    "stretching",
    "mobility",
    "yoga",
    "flexibility",
    "warm up",
    "warmup",
    "smr",
    "foam roll",
    "thoracic rotation",
)

# « rotation » seul rangerait une rotation externe à l'élastique — qui est du
# renforcement de la coiffe — dans la mobilité. Vérifié sur l'échantillon wger
# du 13/09 : c'est la seule erreur que le classement grossier produisait
# systématiquement, et elle se corrige en exigeant le mot entier.
# Le pluriel est admis, et il le faut : les bases ouvertes disent
# « abdominals », « crunches », « stretches ». Exiger le mot exact ferait
# passer la moitié des exercices d'abdos en renforcement.
_WORD_PATTERNS = {
    word: re.compile(rf"(?<![a-z]){re.escape(word)}(?:e?s)?(?![a-z])")
    for word in (*_CORE_WORDS, *_MOBILITY_WORDS)
}


def classify(name: str, hints: Iterable[str]) -> str:
    """Range un exercice importé dans l'une des trois catégories.

    Les indices (catégorie d'origine, muscles, force) sont concaténés au nom :
    la base d'origine dit « stretching » dans un champ et « abs » dans un
    autre, et aucun des deux n'est fiable seul.

    Le classement est **grossier, et on le sait**. Trois catégories parce
    qu'une taxonomie fine se vérifie mal, et qu'un import en apporterait une
    fausse — c'est exactement l'erreur de `sport=surfing`, où une étiquette
    plausible désignait tout autre chose. Le mode `--sample` est là pour qu'on
    la relise avant de l'écrire.
    """
    haystack = " ".join([name, *hints]).lower()
    if any(_WORD_PATTERNS[word].search(haystack) for word in _CORE_WORDS):
        return "core"
    if any(_WORD_PATTERNS[word].search(haystack) for word in _MOBILITY_WORDS):
        return "mobility"
    return "strength"


def strip_html(text: Optional[str]) -> Optional[str]:
    """wger rend du HTML. On garde le texte, et rien d'autre."""
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = " ".join(cleaned.split())
    return cleaned or None


# ── free-exercise-db ───────────────────────────────────────────────────────


async def fetch_free_exercise_db(client: httpx.AsyncClient) -> list[Incoming]:
    """~870 exercices, domaine public, avec images."""
    response = await client.get(FREE_EXERCISE_DB_URL)
    response.raise_for_status()
    payload = response.json()

    out: list[Incoming] = []
    for entry in payload:
        name = (entry.get("name") or "").strip()
        if not name:
            continue

        muscles = list(entry.get("primaryMuscles") or [])
        hints = [
            entry.get("category") or "",
            entry.get("force") or "",
            entry.get("mechanic") or "",
            *muscles,
        ]
        images = [
            f"{FREE_EXERCISE_IMAGE_BASE}{path}"
            for path in (entry.get("images") or [])
        ]

        out.append(
            Incoming(
                name=name,
                category=classify(name, hints),
                muscle_group=muscles[0] if muscles else None,
                instructions=" ".join(entry.get("instructions") or []) or None,
                image_url=images[0] if images else None,
                # Les deux photos : c'est leur alternance qui montre le
                # mouvement, et une seule image ne dit pas ce qui bouge.
                images=images,
                source="free-exercise-db",
                license="Public Domain (Unlicense)",
                source_url="https://github.com/yuhonas/free-exercise-db",
                external_id=str(entry.get("id") or "") or None,
                # free-exercise-db n'a aucune traduction : le glossaire
                # déterministe est le seul recours, et il rend `None` sur ce
                # qu'il ne sait pas dire.
                name_fr=french_name(name),
                taxonomy=classify_taxonomy(
                    name,
                    hints=hints,
                    equipment_hint=entry.get("equipment"),
                    level_hint=entry.get("level"),
                ),
            )
        )
    return out


# ── wger ───────────────────────────────────────────────────────────────────


async def fetch_wger(
    client: httpx.AsyncClient, limit: Optional[int] = None
) -> list[Incoming]:
    """Exercices wger en anglais, avec leurs images quand elles existent.

    `exerciseinfo` et pas `exercisebaseinfo` : wger a renommé l'endpoint, et
    l'ancien rend un 404 (vérifié le 13/09). C'est exactement pour ça que
    l'import ne tombe jamais en marche — un échec de source est journalisé et
    l'autre source continue.

    Une seule ressource suffit : elle embarque les traductions, les muscles,
    les images et la licence de chaque exercice. wger est bénévole comme
    Overpass : on pagine poliment et on s'arrête à la limite demandée.
    """
    out: list[Incoming] = []
    url: Optional[str] = f"{WGER_BASE}/exerciseinfo/?limit=100"

    while url:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()

        for entry in payload.get("results", []):
            translation = next(
                (
                    item
                    for item in entry.get("translations", [])
                    if item.get("language") == WGER_ENGLISH
                ),
                None,
            )
            if translation is None:
                continue

            name = (translation.get("name") or "").strip()
            if not name:
                continue

            # **La traduction humaine d'abord.** wger est traduit par des gens,
            # sous licence libre : ça vaut toujours mieux qu'un glossaire, et
            # c'est gratuit puisque la ressource la porte déjà.
            french = next(
                (
                    item
                    for item in entry.get("translations", [])
                    if item.get("language") == WGER_FRENCH
                ),
                None,
            )

            category = (entry.get("category") or {}).get("name")
            muscles = [
                muscle.get("name_en") or muscle.get("name")
                for muscle in entry.get("muscles", [])
                if muscle.get("name_en") or muscle.get("name")
            ]
            images = entry.get("images") or []
            main_image = next(
                (image.get("image") for image in images if image.get("is_main")),
                images[0].get("image") if images else None,
            )
            # La licence est portée par l'exercice : on la lit sur la ligne au
            # lieu de la supposer. Un contenu contribué peut changer de licence.
            license_name = (entry.get("license") or {}).get("short_name") or (
                "CC-BY-SA-4.0"
            )

            equipment_hint = ", ".join(
                item.get("name", "")
                for item in entry.get("equipment", [])
                if item.get("name")
            )

            out.append(
                Incoming(
                    name=name,
                    category=classify(name, [category or "", *muscles]),
                    muscle_group=muscles[0] if muscles else category,
                    instructions=strip_html(translation.get("description")),
                    image_url=main_image,
                    images=[
                        image.get("image")
                        for image in images
                        if image.get("image")
                    ],
                    source="wger",
                    license=license_name,
                    source_url=f"https://wger.de/en/exercise/{entry.get('id')}/view/",
                    external_id=str(entry.get("id")),
                    name_fr=(
                        (french.get("name") or "").strip() or None
                        if french
                        else None
                    )
                    or french_name(name),
                    description_fr=(
                        strip_html(french.get("description")) if french else None
                    ),
                    taxonomy=classify_taxonomy(
                        name,
                        hints=[category or "", *muscles],
                        equipment_hint=equipment_hint or None,
                        level_hint=None,
                    ),
                )
            )

            if limit is not None and len(out) >= limit:
                return out

        url = payload.get("next")

    return out


# ── Écriture ───────────────────────────────────────────────────────────────


def slugify(name: str) -> str:
    base = normalize_name(name).replace(" ", "-")
    return base[:80] or "exercice"


async def apply(incoming: list[Incoming], dry_run: bool = False) -> Report:
    """Enrichit les exercices rédigés, ajoute le reste, ne supprime jamais rien."""
    report = Report()

    async with async_session() as db:
        rows = (await db.execute(select(Exercise))).scalars().all()

        by_normalized: dict[str, Exercise] = {}
        for exercise in rows:
            by_normalized.setdefault(exercise.name_normalized, exercise)
            for alias in exercise.aliases or []:
                by_normalized.setdefault(normalize_name(alias), exercise)

        taken_slugs = {exercise.slug for exercise in rows}

        for entry in incoming:
            match = by_normalized.get(entry.normalized)

            if match is not None:
                # Une ligne rédigée à la main : on complète ce qui manque,
                # jamais ce qui est à nous. Les consignes françaises restent.
                touched = False
                if match.image_url is None and entry.image_url:
                    match.image_url = entry.image_url
                    touched = True
                if not match.images and entry.images:
                    match.images = list(entry.images)
                    touched = True
                if match.muscle_group is None and entry.muscle_group:
                    match.muscle_group = entry.muscle_group
                    touched = True
                if match.source == "builtin" and entry.image_url:
                    # L'image vient d'ailleurs : sa licence la suit.
                    match.license = f"CC0-1.0 (texte) · {entry.license} (image)"
                    match.source_url = entry.source_url
                    touched = True
                # Un nom français déjà là ne se remplace pas : les lignes rédigées
                # ici sont françaises par construction, et une traduction
                # automatique n'a rien à leur apprendre.
                if not match.name_fr:
                    match.name_fr = entry.name_fr or (
                        match.name if match.source == "builtin" else None
                    )
                    touched = touched or bool(match.name_fr)
                if not match.description_fr and entry.description_fr:
                    match.description_fr = entry.description_fr
                    touched = True
                # La taxonomie **complète** ce qui est encore à classer et ne
                # remplace jamais un classement déjà posé : le catalogue maison
                # est rangé à la main, et une règle grossière n'a pas à le
                # corriger.
                if entry.taxonomy is not None:
                    if match.group_key == UNCLASSIFIED:
                        match.group_key = entry.taxonomy.group
                        touched = touched or match.group_key != UNCLASSIFIED
                    if match.pattern == UNCLASSIFIED:
                        match.pattern = entry.taxonomy.pattern
                        touched = touched or match.pattern != UNCLASSIFIED
                    if match.equipment == UNCLASSIFIED:
                        match.equipment = entry.taxonomy.equipment
                        touched = touched or match.equipment != UNCLASSIFIED
                if touched:
                    report.enriched += 1
                else:
                    report.skipped += 1
                continue

            slug = slugify(entry.name)
            suffix = 2
            while slug in taken_slugs:
                slug = f"{slugify(entry.name)[:76]}-{suffix}"
                suffix += 1
            taken_slugs.add(slug)

            taxonomy = entry.taxonomy
            exercise = Exercise(
                slug=slug,
                name=entry.name,
                name_normalized=entry.normalized,
                category=entry.category,
                muscle_group=entry.muscle_group,
                instructions=entry.instructions,
                image_url=entry.image_url,
                images=list(entry.images) or None,
                source=entry.source,
                license=entry.license,
                source_url=entry.source_url,
                external_id=entry.external_id,
                name_fr=entry.name_fr,
                description_fr=entry.description_fr,
                group_key=taxonomy.group if taxonomy else UNCLASSIFIED,
                pattern=taxonomy.pattern if taxonomy else UNCLASSIFIED,
                equipment=taxonomy.equipment if taxonomy else UNCLASSIFIED,
                difficulty=taxonomy.difficulty if taxonomy else 3,
                effort_kind=taxonomy.effort if taxonomy else "reps",
                unilateral=taxonomy.unilateral if taxonomy else False,
            )
            by_normalized[entry.normalized] = exercise
            report.created += 1
            if not dry_run:
                db.add(exercise)

        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    return report


def print_sample(incoming: list[Incoming], count: int = 25) -> None:
    """Montre un échantillon et **n'écrit rien**.

    À lancer avant tout import complet. La leçon de `sport=surfing` est qu'une
    étiquette plausible peut désigner tout autre chose : on regarde d'abord si
    le classement tient, on importe ensuite.

    Depuis le 13/09, ce tableau montre aussi le **nom français** et la
    **taxonomie**. Ce qu'il faut y lire en priorité, ce sont les lignes
    « — rien — » et les « a-classer » : elles sont voulues. Un exercice qu'on
    ne sait pas nommer ou ranger reste dehors, il n'est jamais deviné.
    """
    print(f"\n{len(incoming)} exercices récupérés. Échantillon de {count} :\n")
    print(
        f"  {'NOM ANGLAIS':<38} {'NOM FRANÇAIS':<30} {'GROUPE':<13} "
        f"{'PATTERN':<18} {'MATÉRIEL':<16} D  IMG"
    )
    print("  " + "─" * 122)

    step = max(1, len(incoming) // count)
    for entry in incoming[::step][:count]:
        taxonomy = entry.taxonomy
        print(
            f"  {entry.name[:37]:<38} "
            f"{(entry.name_fr or '— rien —')[:29]:<30} "
            f"{(taxonomy.group if taxonomy else '?')[:12]:<13} "
            f"{(taxonomy.pattern if taxonomy else '?')[:17]:<18} "
            f"{(taxonomy.equipment if taxonomy else '?')[:15]:<16} "
            f"{taxonomy.difficulty if taxonomy else '?'}  "
            f"{len(entry.images)}"
        )

    def tally(getter) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in incoming:
            key = getter(entry)
            counts[key] = counts.get(key, 0) + 1
        return counts

    for title, getter in (
        ("catégorie", lambda e: e.category),
        ("groupe", lambda e: e.taxonomy.group if e.taxonomy else "?"),
        ("pattern", lambda e: e.taxonomy.pattern if e.taxonomy else "?"),
        ("matériel", lambda e: e.taxonomy.equipment if e.taxonomy else "?"),
    ):
        print(f"\nRépartition par {title} :")
        for key, value in sorted(tally(getter).items(), key=lambda pair: -pair[1]):
            print(f"  {key:<20} {value}")

    translated = sum(1 for entry in incoming if entry.name_fr)
    with_image = sum(1 for entry in incoming if entry.image_url)
    eligible = sum(
        1
        for entry in incoming
        if entry.name_fr
        and entry.image_url
        and entry.taxonomy
        and entry.taxonomy.classified
    )
    total = len(incoming) or 1
    print(
        f"\nNom français : {translated}/{total}"
        f" · avec image : {with_image}/{total}"
        f" · **éligibles au générateur** : {eligible}/{total}"
    )
    print(
        "\nRien n'a été écrit. Relis le classement ci-dessus avant "
        "d'importer pour de bon.\n"
    )


async def run(args: argparse.Namespace) -> None:
    async with httpx.AsyncClient(
        timeout=TIMEOUT_S, headers={"User-Agent": "sport-app/0.1 (perso)"}
    ) as client:
        incoming: list[Incoming] = []

        if args.source in {"free", "all"}:
            try:
                free = await fetch_free_exercise_db(client)
                logger.info("free-exercise-db : %d exercices", len(free))
                incoming.extend(free)
            except Exception as exc:
                logger.error("free-exercise-db injoignable : %s", exc)

        if args.source in {"wger", "all"}:
            try:
                wger = await fetch_wger(client, limit=args.limit)
                logger.info("wger : %d exercices", len(wger))
                incoming.extend(wger)
            except Exception as exc:
                logger.error("wger injoignable : %s", exc)

    if not incoming:
        logger.error("Aucun exercice récupéré. Rien à faire.")
        return

    if args.sample:
        print_sample(incoming, count=args.sample)
        return

    report = await apply(incoming, dry_run=args.dry_run)
    logger.info(
        "%s : %d enrichis, %d créés, %d inchangés",
        "Simulation" if args.dry_run else "Import",
        report.enriched,
        report.created,
        report.skipped,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importe des exercices depuis wger et free-exercise-db."
    )
    parser.add_argument(
        "--source",
        choices=["all", "wger", "free"],
        default="all",
        help="Source à interroger (défaut : les deux).",
    )
    parser.add_argument(
        "--sample",
        nargs="?",
        type=int,
        const=40,
        default=None,
        metavar="N",
        help=(
            "Montre N lignes classées et n'écrit rien (40 par défaut). "
            "À faire en premier, et à relire."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compte ce qui serait écrit, sans rien écrire.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Plafond d'exercices wger, pour un import partiel.",
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
