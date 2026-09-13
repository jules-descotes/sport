"""Import de la table Ciqual — composition nutritionnelle des aliments (ANSES).

    python -m scripts.import_ciqual --sample
    python -m scripts.import_ciqual --file data/ciqual.csv

Source : table Ciqual de l'ANSES, publiée sur data.gouv.fr. Base publique,
française, complète, et la seule qui décrive des aliments plutôt que des
produits de marque — c'est ce qu'il faut pour une recette et pour une pesée.

**`--sample` d'abord, comme toujours.** Il affiche une trentaine de lignes et
n'écrit rien. C'est la leçon de `sport=surfing`, appliquée : on regarde la
donnée avant de s'y fier. Une colonne mal devinée remplirait la base de
calories nulles, et on ne s'en apercevrait qu'au premier repas journalisé.

**Ce qu'on garde** : le nom, le groupe, et cinq grandeurs pour 100 g —
énergie, protéines, glucides, lipides, fibres. Le reste de la table (une
soixantaine de colonnes, des vitamines aux acides gras individuels) est
volontairement laissé de côté : on ne stocke pas large ici, parce que ces
colonnes-là ne nourriront jamais aucun modèle et alourdiraient chaque
recherche.

**Les valeurs de Ciqual ne sont pas des nombres.** On y trouve « traces »,
« - », « < 0,1 » et des virgules décimales. Chacune est traitée pour ce qu'elle
est : `traces` et `< x` valent zéro, `-` vaut *inconnu* — et un inconnu reste
`NULL`, jamais zéro. Un zéro se lirait « cet aliment n'a pas de protéines ».

L'import est **idempotent** sur `(source, external_id)` : on peut le rejouer
autant qu'on veut, y compris sur une nouvelle version de la table.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import logging
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session
from app.models.nutrition import Food

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ciqual")

SOURCE = "ciqual"
DEFAULT_VERSION = "ciqual-2025"

# Les colonnes qu'on cherche, par **fragments** de leur intitulé. Ciqual change
# la ponctuation et les unités entre deux versions (« Energie, Règlement UE
# N° 1169/2011 (kcal/100 g) ») : chercher un intitulé exact casserait au
# premier millésime. On cherche donc des fragments, tous présents.
COLUMN_HINTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "external_id": (("alim_code",), ("code",)),
    "name": (("alim_nom_fr",), ("nom", "fr")),
    "food_group": (("alim_grp_nom_fr",), ("groupe",)),
    "kcal_100g": (("energie", "kcal"),),
    "protein_100g": (("proteines",), ("protéines",)),
    "carb_100g": (("glucides",),),
    "fat_100g": (("lipides",),),
    "fiber_100g": (("fibres",),),
}

# Combien de lignes `--sample` montre. Assez pour repérer une colonne décalée,
# assez peu pour tenir dans un terminal.
SAMPLE_SIZE = 30

_CHUNK = 200


def strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )


def normalize(value: str) -> str:
    """Minuscules, sans accents, espaces resserrés — la clé de recherche."""
    return " ".join(strip_accents(value).lower().split())


def parse_number(raw: Optional[str]) -> Optional[float]:
    """Une valeur Ciqual vers un nombre, ou `None` si elle est inconnue.

    - `traces`, `< 0,1` : la quantité est négligeable, donc **zéro** ;
    - `-`, vide, `NA` : la valeur n'a pas été mesurée, donc **inconnue**. Elle
      reste `NULL` : la mettre à zéro ferait croire que l'aliment n'en contient
      pas, ce qui est une affirmation qu'on n'a pas.
    """
    if raw is None:
        return None
    text = raw.strip().replace(" ", " ")
    if not text or text in {"-", "NA", "ND"}:
        return None
    lowered = strip_accents(text).lower()
    if "trace" in lowered:
        return 0.0
    if text.startswith("<"):
        return 0.0
    try:
        return float(text.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def find_column(headers: Iterable[str], hints: tuple[tuple[str, ...], ...]) -> Optional[str]:
    """La première colonne dont l'intitulé contient tous les fragments d'un indice."""
    normalized = [(header, normalize(header)) for header in headers]
    for fragments in hints:
        for header, flat in normalized:
            if all(fragment in flat for fragment in fragments):
                return header
    return None


def map_columns(headers: list[str]) -> dict[str, str]:
    """Associe nos champs aux colonnes du fichier, et dit ce qui manque."""
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for field, hints in COLUMN_HINTS.items():
        column = find_column(headers, hints)
        if column is None:
            missing.append(field)
        else:
            mapping[field] = column

    # Le nom et le code sont indispensables : sans eux, il n'y a pas d'aliment.
    for required in ("external_id", "name"):
        if required in missing:
            raise SystemExit(
                f"Colonne introuvable pour « {required} ».\n"
                f"Colonnes du fichier : {', '.join(headers[:12])}…"
            )
    if missing:
        logger.warning(
            "Colonnes absentes, laissées vides : %s", ", ".join(missing)
        )
    return mapping


def read_rows(path: Path) -> Iterator[dict[str, str]]:
    """Lit le CSV, quel que soit son encodage et son séparateur.

    Ciqual est publié en UTF-8 sur data.gouv.fr et en Latin-1 dans certaines
    reprises, avec un point-virgule comme séparateur en français. On essaie, on
    ne suppose pas.
    """
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - un fichier illisible reste illisible
        raise SystemExit(f"Encodage non reconnu pour {path}")

    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    yield from csv.DictReader(io.StringIO(text), delimiter=delimiter)


def build_food(row: dict[str, str], mapping: dict[str, str], version: str) -> Optional[dict]:
    """Une ligne de CSV vers une ligne de `foods`. `None` si elle est inutilisable."""
    code = (row.get(mapping["external_id"]) or "").strip()
    name = (row.get(mapping["name"]) or "").strip()
    if not code or not name:
        return None

    values = {
        field: parse_number(row.get(column))
        for field, column in mapping.items()
        if field not in ("external_id", "name", "food_group")
    }

    return {
        "source": SOURCE,
        "source_version": version,
        "external_id": code,
        "name": name,
        "name_normalized": normalize(name),
        "food_group": (
            (row.get(mapping["food_group"]) or "").strip() or None
            if "food_group" in mapping
            else None
        ),
        "kcal_100g": values.get("kcal_100g"),
        "protein_100g": values.get("protein_100g"),
        "carb_100g": values.get("carb_100g"),
        "fat_100g": values.get("fat_100g"),
        "fiber_100g": values.get("fiber_100g"),
    }


async def upsert_foods(db: AsyncSession, payload: list[dict]) -> int:
    """Écrit les aliments. Idempotent sur `(source, external_id)`."""
    if not payload:
        return 0

    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert

    written = 0
    for start in range(0, len(payload), _CHUNK):
        chunk = payload[start : start + _CHUNK]
        statement = insert(Food).values(chunk)
        # Un rejeu sur une nouvelle version doit **mettre à jour** : c'est tout
        # l'intérêt d'avoir la version sur la ligne.
        statement = statement.on_conflict_do_update(
            index_elements=["source", "external_id"],
            set_={
                column: getattr(statement.excluded, column)
                for column in (
                    "name",
                    "name_normalized",
                    "food_group",
                    "source_version",
                    "kcal_100g",
                    "protein_100g",
                    "carb_100g",
                    "fat_100g",
                    "fiber_100g",
                )
            },
        )
        await db.execute(statement)
        written += len(chunk)

    await db.commit()
    return written


def show_sample(foods: list[dict]) -> None:
    """Affiche un échantillon et **n'écrit rien**.

    On regarde la donnée avant de s'y fier : une colonne mal devinée remplirait
    la base de calories nulles, et on ne s'en apercevrait qu'au premier repas
    journalisé.
    """
    print(f"{len(foods)} aliments lus. Echantillon :\n")
    print(f"{'code':>8}  {'kcal':>6} {'prot':>6} {'gluc':>6} {'lip':>6} {'fib':>6}  nom")
    for food in foods[:SAMPLE_SIZE]:
        def cell(value: Optional[float]) -> str:
            return "-" if value is None else f"{value:.1f}"

        print(
            f"{food['external_id']:>8}  "
            f"{cell(food['kcal_100g']):>6} "
            f"{cell(food['protein_100g']):>6} "
            f"{cell(food['carb_100g']):>6} "
            f"{cell(food['fat_100g']):>6} "
            f"{cell(food['fiber_100g']):>6}  "
            f"{food['name'][:60]}"
        )

    unknown = sum(1 for food in foods if food["kcal_100g"] is None)
    print(f"\n{unknown} aliments sans energie ({unknown * 100 // max(1, len(foods))} %).")
    print("Rien n'a ete ecrit. Relance sans --sample si les colonnes tiennent.")


async def run(path: Path, version: str, sample: bool, limit: Optional[int]) -> int:
    rows = list(read_rows(path))
    if not rows:
        raise SystemExit(f"{path} ne contient aucune ligne.")

    mapping = map_columns(list(rows[0].keys()))
    logger.info("Colonnes retenues : %s", mapping)

    foods = [build_food(row, mapping, version) for row in rows]
    foods = [food for food in foods if food is not None]
    if limit:
        foods = foods[:limit]

    if sample:
        show_sample(foods)
        return 0

    async with async_session() as db:
        written = await upsert_foods(db, foods)
        total = (
            await db.execute(select(func.count()).select_from(Food))
        ).scalar_one()

    logger.info("%d aliments ecrits, %d en base au total", written, total)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import de la table Ciqual")
    parser.add_argument(
        "--file",
        default="data/ciqual.csv",
        help="CSV Ciqual (data.gouv.fr). Defaut : data/ciqual.csv",
    )
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Affiche un echantillon et n'ecrit rien.",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(
            f"{path} introuvable.\n"
            "Telecharge la table Ciqual sur data.gouv.fr "
            "(ANSES, « Table de composition nutritionnelle Ciqual ») "
            "et pose le CSV a cet endroit."
        )

    return asyncio.run(run(path, args.version, args.sample, args.limit))


if __name__ == "__main__":
    sys.exit(main())
