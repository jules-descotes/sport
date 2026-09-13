"""Open Food Facts — le complément au code-barres.

Ciqual décrit des **aliments** : « riz blanc cuit », « blanc de poulet ». C'est
ce qu'il faut pour une recette et pour une pesée. Open Food Facts décrit des
**produits** : le paquet de céréales précis qu'on a dans le placard. Les deux
se complètent, et c'est pour ça qu'ils cohabitent dans la même table `foods`.

Deux règles, toutes les deux issues du cadrage :

- **À la demande seulement.** On n'importe pas Open Food Facts : c'est une base
  de trois millions de produits dont on utilisera cinquante. On interroge quand
  un code-barres est scanné, et on met en cache ce qu'on a scanné.
- **Ce qui a été scanné reste.** Le produit devient une ligne `foods` locale,
  et le prochain scan du même paquet ne sort plus sur le réseau — ni sur le
  parking, ni dans la cuisine où le wifi ne passe pas.

Gratuit, sans clé, en usage non commercial, comme Open-Meteo et Overpass. On
s'annonce dans le `User-Agent` : c'est ce que demandent leurs conditions, et
c'est la moindre des politesses envers une base bénévole.
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.nutrition import Food

logger = logging.getLogger(__name__)

SOURCE = "openfoodfacts"

# Seuls les champs utiles sont demandés : la fiche complète d'un produit fait
# plusieurs dizaines de kilo-octets, et on en garde cinq nombres.
FIELDS = (
    "code",
    "product_name",
    "product_name_fr",
    "brands",
    "categories",
    "nutriments",
)

TIMEOUT_S = 6.0


def normalize(value: str) -> str:
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(stripped.lower().split())


def _number(nutriments: dict[str, Any], *keys: str) -> Optional[float]:
    """La première valeur présente parmi plusieurs clés possibles.

    Open Food Facts est rempli par des bénévoles : le même nutriment s'y trouve
    sous `energy-kcal_100g`, `energy-kcal_value` ou rien du tout. On essaie, on
    ne suppose pas — et une absence reste une absence, jamais un zéro.
    """
    for key in keys:
        value = nutriments.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def parse_product(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Une fiche Open Food Facts vers une ligne `foods`.

    Rend `None` si le produit n'a ni nom ni énergie : une ligne sans calories
    ne sert à rien au journal, et l'ajouter ferait grossir la base de bruit.
    """
    product = payload.get("product") or {}
    code = str(product.get("code") or "").strip()
    name = (
        product.get("product_name_fr")
        or product.get("product_name")
        or ""
    ).strip()
    if not code or not name:
        return None

    nutriments = product.get("nutriments") or {}
    kcal = _number(nutriments, "energy-kcal_100g", "energy-kcal_value")
    if kcal is None:
        # Certaines fiches ne portent que les kilojoules.
        kj = _number(nutriments, "energy_100g", "energy-kj_100g")
        kcal = None if kj is None else round(kj / 4.184, 1)
    if kcal is None:
        return None

    brand = (product.get("brands") or "").split(",")[0].strip() or None

    return {
        "source": SOURCE,
        "source_version": None,
        "external_id": code,
        "barcode": code,
        "name": name if not brand else f"{name} ({brand})",
        "name_normalized": normalize(f"{name} {brand or ''}"),
        "brand": brand,
        "food_group": (product.get("categories") or "").split(",")[0].strip()
        or None,
        "kcal_100g": kcal,
        "protein_100g": _number(nutriments, "proteins_100g"),
        "carb_100g": _number(nutriments, "carbohydrates_100g"),
        "fat_100g": _number(nutriments, "fat_100g"),
        "fiber_100g": _number(nutriments, "fiber_100g"),
    }


async def fetch_product(
    barcode: str, client: Optional[httpx.AsyncClient] = None
) -> Optional[dict[str, Any]]:
    """Interroge Open Food Facts. Rend `None` sur échec — jamais une exception.

    Un scan qui échoue doit laisser la saisie manuelle possible, pas casser
    l'écran : c'est la même règle que le backfill d'archive d'une session.
    """
    url = f"{settings.openfoodfacts_url.rstrip('/')}/api/v2/product/{barcode}.json"
    params = {"fields": ",".join(FIELDS)}
    headers = {"User-Agent": settings.openfoodfacts_user_agent}

    async def _run(http: httpx.AsyncClient) -> Optional[dict[str, Any]]:
        response = await http.get(url, params=params, headers=headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == 0:
            return None
        return parse_product(payload)

    try:
        if client is not None:
            return await _run(client)
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S)) as http:
            return await _run(http)
    except Exception as exc:
        logger.warning("Open Food Facts injoignable pour %s : %s", barcode, exc)
        return None


async def lookup_barcode(
    db: AsyncSession,
    barcode: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[Food]:
    """Le produit du code-barres : d'abord la base locale, puis le réseau.

    Le cache n'est pas une optimisation, c'est une condition de fonctionnement :
    on scanne dans une cuisine où le wifi ne passe pas, et le même paquet de
    céréales revient toutes les semaines.
    """
    code = barcode.strip()
    if not code:
        return None

    cached = (
        await db.execute(select(Food).where(Food.barcode == code))
    ).scalar_one_or_none()
    if cached is not None:
        return cached

    payload = await fetch_product(code, client)
    if payload is None:
        return None

    food = Food(**payload)
    db.add(food)
    await db.commit()
    await db.refresh(food)
    logger.info("Produit mis en cache depuis Open Food Facts : %s", food.name)
    return food
