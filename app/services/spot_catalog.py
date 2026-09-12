"""Catalogue de spots — slugs, résolution, et création manuelle.

Partagé entre l'API (ajout depuis la carte) et le script d'import OSM, pour que
les deux produisent exactement les mêmes slugs. Un spot importé et un spot
ajouté à la main doivent être indiscernables à l'usage ; seule la colonne
`source` les distingue, et elle ne sert qu'à protéger les seconds du rejeu
mensuel des premiers.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spot import Spot

SLUG_MAX_LENGTH = 60


def slugify(value: str) -> str:
    """Kebab-case sans accent (cf. CLAUDE.md, conventions).

    Le catalogue est mondial : les noms arrivent en japonais, en grec ou en
    arabe, et une translittération ASCII en sort parfois vide. Le repli est
    géré par `unique_slug`, qui a sous la main de quoi fabriquer un identifiant.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug[:SLUG_MAX_LENGTH].strip("-")


async def unique_slug(
    db: AsyncSession, name: str, fallback: str, exclude_id: Optional[int] = None
) -> str:
    """Slug libre pour `name`, suffixé au besoin.

    Il y a plusieurs « la Piste » et plusieurs « Beach Break » dans le monde :
    le suffixe numérique est la règle, pas l'exception.
    """
    base = slugify(name) or slugify(fallback) or "spot"

    candidate = base
    suffix = 2
    while True:
        query = select(Spot.id).where(Spot.slug == candidate)
        if exclude_id is not None:
            query = query.where(Spot.id != exclude_id)
        existing = (await db.execute(query)).scalar_one_or_none()
        if existing is None:
            return candidate
        candidate = f"{base[: SLUG_MAX_LENGTH - 5]}-{suffix}"
        suffix += 1


async def resolve_spot(db: AsyncSession, reference: Union[int, str]) -> Optional[Spot]:
    """Retrouve un spot par identifiant numérique ou par slug.

    Le front navigue en slugs (`/surf/spots/les-cavaliers`), les liens internes
    en identifiants : accepter les deux évite un aller-retour de résolution à
    chaque écran.
    """
    text = str(reference)
    query = (
        select(Spot).where(Spot.id == int(text))
        if text.isdigit()
        else select(Spot).where(Spot.slug == text)
    )
    return (await db.execute(query)).scalar_one_or_none()
