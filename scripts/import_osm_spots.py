"""Import du catalogue mondial de spots depuis OpenStreetMap.

Rejouable tous les mois, idempotent, et **il ne touche jamais aux spots
`source='user'`** : ceux-là sont la seule donnée du catalogue qui n'est pas
reconstituable, ils ont été ajoutés à la main depuis la carte là où OSM est
vide.

⚠️ **`sport=surfing` ne désigne pas des spots.** Relevé fait sur le terrain :
sur la côte basco-landaise, les 68 objets `sport=surfing` sont *tous* des
magasins, des écoles ou des clubs — pas un seul spot. Même constat à Santa Cruz
et sur la Gold Coast. Les vrais spots sont, eux, dans `natural=beach` nommées
(Plage de la Gravière, Les Culs Nus, Parlementia, Pavillon Royal…) et dans
`natural=reef`. L'import ratisse donc trois sources et écarte explicitement le
commerce :

1. `sport=surfing` **dépouillé** des objets portant `shop`, `club`, `amenity`,
   `office`, `tourism`, `craft`, `building` ou `leisure` — ce qui laisse les
   pics réellement nommés (« Cave », « Crazy Left » à Ericeira) ;
2. `natural=beach` nommées ;
3. `natural=reef` nommés.

Trois passes :

1. **Candidats** — la requête ci-dessus, nœuds plus centroïdes des zones et des
   relations.
2. **Trait de côte** — pour chaque candidat, le cap du segment
   `natural=coastline` le plus proche, lissé sur 500 m. Les lignes de côte OSM
   sont tracées **terre à gauche, mer à droite** : la normale sortante est le
   cap + 90°, ce qui donne `onshore_dir_deg` sans aucune ambiguïté. Un candidat
   à plus de `MAX_COAST_DISTANCE_M` de la mer est écarté ici — c'est le filtre
   qui élimine les plages de lac, les vagues de rivière et les magasins restés
   dans les mailles du filet.
3. **Écriture** — upsert sur la clé naturelle `(osm_type, osm_id)`, **et
   suppression** des spots `source='osm'` que le filtre côtier vient d'écarter :
   sans ça, une plage de lac entrée pendant un passage dégradé resterait au
   catalogue pour toujours.

   Le trait de côte n'est pas interrogé spot par spot — ce serait des milliers
   de requêtes Overpass. Les candidats sont regroupés en tuiles, et une requête
   par tuile rapporte tout le trait de côte de la zone.

**Quand Overpass bloque**, on n'enchaîne pas les tuiles suivantes : un import
réel en a perdu 49 d'affilée comme ça, parce que continuer à frapper une
instance qui refuse les connexions ne fait que prolonger le bannissement. On
attend 60 s, puis 120 s, puis 300 s, en reprenant **la même tuile** à chaque
fois, et on n'abandonne qu'après. Les tuiles finalement perdues sont listées en
fin de run avec la commande `--bbox` qui les rejoue.

Une tuile abandonnée rend ses candidats **sans orientation et sans filtrage** :
un import dégradé ne doit jamais déclencher de suppression.

Ce calcul vit **ici et nulle part ailleurs** : jamais à la volée dans l'API
(cf. CLAUDE.md). Une orientation de plage est de toute façon un *a priori* de
cold start, abandonné spot par spot dès qu'un spot atteint ~25 sessions notées
(cf. PROJET.md §7.4) — la précision au degré près n'a aucun intérêt.

Usage :
    python -m scripts.import_osm_spots                    # le monde entier
    python -m scripts.import_osm_spots --bbox 43.3,-1.8,43.75,-1.3
    python -m scripts.import_osm_spots --skip-coastline
    python -m scripts.import_osm_spots --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import sys
import time
from collections import defaultdict
from typing import Any, Iterable, Optional, Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import async_session
from app.models.enums import SpotSource, SpotType
from app.models.spot import Spot, SpotPreference
from app.models.surf_session import SurfSession
from app.services.geo import (
    Point,
    nearest_coast_bearing,
    onshore_from_coast_bearing,
)
from app.services.spot_catalog import slugify

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s"
)
logger = logging.getLogger("import_osm_spots")

# Overpass est un service bénévole : une requête mondiale est déjà lourde, on
# ne la lance qu'une fois par mois et on laisse respirer entre deux tuiles.
# Un agent identifiable est demandé par leur politique d'usage.
USER_AGENT = "sport-atelier-okomi/1.0 (import mensuel de spots de surf)"
OVERPASS_TIMEOUT_S = 900
# Espacement minimal entre deux requêtes, garanti par `_throttle`.
PAUSE_BETWEEN_QUERIES_S = 2.0
MAX_RETRIES = 3

# Attentes longues, appliquées à la **même tuile** quand Overpass bloque.
# Enchaîner les tuiles suivantes pendant un bannissement ne fait que le
# prolonger : un import réel a perdu 49 tuiles d'affilée comme ça. On attend,
# on reprend la même tuile, et on n'abandonne qu'après la dernière attente.
BLOCKED_BACKOFF_S = (60.0, 120.0, 300.0)

# Horodatage de la dernière requête Overpass, pour `_throttle`.
_last_request_at: Optional[float] = None

# Clés qui trahissent un commerce, un club ou un bâtiment plutôt qu'un spot.
# Un objet qui en porte une est écarté, quel que soit son `sport`.
BUSINESS_KEYS = (
    "shop",
    "club",
    "amenity",
    "office",
    "tourism",
    "craft",
    "building",
    "leisure",
    "healthcare",
)

# Côté du carreau de regroupement des candidats pour la requête de trait de
# côte. 0,5° ≈ 55 km : assez large pour amortir la requête, assez petit pour
# que la réponse tienne en mémoire.
COAST_TILE_DEG = 0.5
# Marge autour de la tuile : un spot au bord doit trouver le trait de côte qui
# dépasse de l'autre côté de la frontière.
COAST_PADDING_DEG = 0.15
# Au-delà, ce n'est pas un spot de surf : plage de lac, vague de rivière, ou
# magasin oublié par le filtre. Le candidat est écarté, pas seulement laissé
# sans orientation.
MAX_COAST_DISTANCE_M = 5_000.0

# Étiquettes OSM conservées telles quelles : la couverture est inégale et on ne
# sait pas encore ce qui servira.
KEPT_TAGS = (
    "name",
    "name:en",
    "natural",
    "surface",
    "sport",
    "seamark:type",
    "website",
    "webcam",
    "description",
    "addr:country",
    "is_in:country_code",
)

SPOT_TYPE_BY_SURFACE = {
    "reef": SpotType.REEF.value,
    "sand": SpotType.BEACH.value,
    "gravel": SpotType.BEACH.value,
    "pebbles": SpotType.BEACH.value,
    "rock": SpotType.REEF.value,
}


def spots_query(bbox: Optional[str]) -> str:
    """Candidats de spot : pics nommés, plages nommées, récifs nommés.

    Le filtre `[!shop][!club]…` est posé dans la requête plutôt qu'à la
    lecture : sur une requête mondiale, ça évite de rapatrier des dizaines de
    milliers de magasins pour les jeter ensuite.
    """
    area = f"({bbox})" if bbox else ""
    exclusions = "".join(f"[!{key}]" for key in BUSINESS_KEYS)
    return f"""
[out:json][timeout:{OVERPASS_TIMEOUT_S}];
(
  node["sport"="surfing"]{exclusions}{area};
  way["sport"="surfing"]{exclusions}{area};
  relation["sport"="surfing"]{exclusions}{area};
  node["natural"="beach"]["name"]{area};
  way["natural"="beach"]["name"]{area};
  relation["natural"="beach"]["name"]{area};
  node["natural"="reef"]["name"]{area};
  way["natural"="reef"]["name"]{area};
);
out center tags;
""".strip()


def coastline_query(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> str:
    return f"""
[out:json][timeout:{OVERPASS_TIMEOUT_S}];
way["natural"="coastline"]({min_lat},{min_lon},{max_lat},{max_lon});
out geom;
""".strip()


async def _throttle() -> None:
    """Garantit `PAUSE_BETWEEN_QUERIES_S` entre deux requêtes, quoi qu'il arrive.

    L'espacement est posé ici et pas dans la boucle des tuiles : une tuile en
    échec, une reprise après attente longue ou un `continue` quelconque
    sautaient la pause et enchaînaient les requêtes — ce qui est exactement ce
    qui déclenche le blocage.
    """
    global _last_request_at

    if _last_request_at is not None:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < PAUSE_BETWEEN_QUERIES_S:
            await asyncio.sleep(PAUSE_BETWEEN_QUERIES_S - elapsed)

    _last_request_at = time.monotonic()


def is_throttled(exc: BaseException) -> bool:
    """L'erreur trahit-elle un blocage d'Overpass plutôt qu'une requête fautive ?

    Deux formes, vues sur un import réel : le 429 qui survit aux trois
    tentatives courtes, et le « All connection attempts failed » — l'instance
    refuse la connexion avant même de répondre, ce qui est sa façon de bannir
    un client trop pressé. Une requête mal écrite (400) ou un objet introuvable
    n'ont, eux, aucune raison d'être rejoués huit minutes plus tard.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 502, 503, 504)
    return False


async def overpass(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    """Appel Overpass avec backoff court — 429 et 504 sont la norme.

    Les attentes longues, elles, sont gérées un cran au-dessus, par tuile
    (cf. `fetch_coastline`) : ce n'est pas la même décision. Ici on absorbe un
    hoquet ; là-haut on décide d'attendre cinq minutes ou d'abandonner.
    """
    delay = 5.0
    for attempt in range(1, MAX_RETRIES + 1):
        await _throttle()
        # Overpass attend la requête en `data=` encodé en formulaire ; un corps
        # brut se fait renvoyer un 406 par l'instance principale.
        response = await client.post(
            settings.overpass_url,
            data={"data": query},
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code in (429, 504) and attempt < MAX_RETRIES:
            logger.warning(
                "Overpass %d — nouvelle tentative dans %.0f s (%d/%d)",
                response.status_code,
                delay,
                attempt,
                MAX_RETRIES,
            )
            await asyncio.sleep(delay)
            delay *= 2
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("Overpass injoignable")  # pragma: no cover


# ── Passe 1 : les candidats ────────────────────────────────────────────────


def is_business(tags: dict[str, str]) -> bool:
    """Deuxième filet, à la lecture : Overpass peut servir un cache plus ancien."""
    return any(key in tags for key in BUSINESS_KEYS)


def _spot_type(tags: dict[str, str]) -> str:
    if tags.get("natural") == "reef":
        return SpotType.REEF.value
    surface = SPOT_TYPE_BY_SURFACE.get(tags.get("surface", ""))
    if surface:
        return surface
    if tags.get("natural") == "beach":
        return SpotType.BEACH.value
    return SpotType.UNKNOWN.value


def _country_code(tags: dict[str, str]) -> Optional[str]:
    raw = tags.get("is_in:country_code") or tags.get("addr:country") or ""
    code = raw.strip().upper()
    return code if len(code) == 2 else None


def parse_elements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise les éléments Overpass en candidats de spot.

    Un `way` ou une `relation` n'a pas de coordonnée propre : Overpass en donne
    le centroïde avec `out center`. Un objet sans nom est écarté — un spot sans
    nom n'est pas choisissable dans une liste, et OSM en compte beaucoup.
    """
    candidates: list[dict[str, Any]] = []

    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        name = (tags.get("name") or tags.get("name:en") or "").strip()
        if not name or is_business(tags):
            continue

        if element.get("type") == "node":
            lat, lon = element.get("lat"), element.get("lon")
        else:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")

        if lat is None or lon is None:
            continue

        candidates.append(
            {
                "osm_type": element["type"],
                "osm_id": int(element["id"]),
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "country_code": _country_code(tags),
                "spot_type": _spot_type(tags),
                "tags": {key: tags[key] for key in KEPT_TAGS if key in tags},
                # Renseignés par la passe 2.
                "coast_bearing_deg": None,
                "onshore_dir_deg": None,
                "coast_distance_m": None,
            }
        )

    return candidates


# ── Passe 2 : le trait de côte ─────────────────────────────────────────────


def parse_coastlines(payload: dict[str, Any]) -> list[list[Point]]:
    """Extrait les polylignes `natural=coastline` d'une réponse `out geom`."""
    ways: list[list[Point]] = []
    for element in payload.get("elements", []):
        geometry = element.get("geometry") or []
        points = [
            (float(node["lat"]), float(node["lon"]))
            for node in geometry
            if node.get("lat") is not None and node.get("lon") is not None
        ]
        if len(points) >= 2:
            ways.append(points)
    return ways


def tile_of(lat: float, lon: float) -> tuple[int, int]:
    return (
        math.floor(lat / COAST_TILE_DEG),
        math.floor(lon / COAST_TILE_DEG),
    )


def tile_bbox(tile: tuple[int, int]) -> tuple[float, float, float, float]:
    lat_index, lon_index = tile
    return (
        lat_index * COAST_TILE_DEG - COAST_PADDING_DEG,
        lon_index * COAST_TILE_DEG - COAST_PADDING_DEG,
        (lat_index + 1) * COAST_TILE_DEG + COAST_PADDING_DEG,
        (lon_index + 1) * COAST_TILE_DEG + COAST_PADDING_DEG,
    )


def coast_orientation(
    lat: float, lon: float, ways: Iterable[Sequence[Point]]
) -> Optional[dict[str, float]]:
    """Orientation du trait de côte le plus proche.

    Renvoie `None` s'il n'y a pas de côte exploitable dans le rayon : ce n'est
    alors pas un spot de surf, et une orientation inventée serait pire qu'une
    absence d'orientation.
    """
    found = nearest_coast_bearing(lat, lon, ways)
    if found is None:
        return None

    bearing, distance_m = found
    if distance_m > MAX_COAST_DISTANCE_M:
        return None

    return {
        "coast_bearing_deg": round(bearing, 1),
        "onshore_dir_deg": round(onshore_from_coast_bearing(bearing), 1),
        "coast_distance_m": round(distance_m, 1),
    }


async def fetch_coastline(
    client: httpx.AsyncClient, tile: tuple[int, int]
) -> list[list[Point]]:
    """Trait de côte d'une tuile, avec attentes longues si Overpass bloque.

    Lève la dernière exception si la tuile reste injoignable après toutes les
    attentes — l'appelant décide quoi en faire.
    """
    min_lat, min_lon, max_lat, max_lon = tile_bbox(tile)
    query = coastline_query(min_lat, min_lon, max_lat, max_lon)

    attempts = len(BLOCKED_BACKOFF_S) + 1
    for attempt in range(attempts):
        try:
            return parse_coastlines(await overpass(client, query))
        except Exception as exc:
            last = attempt == attempts - 1
            if last or not is_throttled(exc):
                raise
            wait = BLOCKED_BACKOFF_S[attempt]
            logger.warning(
                "Overpass bloque sur la tuile %s (%s) — pause de %.0f s avant "
                "de reprendre la MÊME tuile (%d/%d)",
                tile,
                type(exc).__name__,
                wait,
                attempt + 1,
                len(BLOCKED_BACKOFF_S),
            )
            await asyncio.sleep(wait)

    raise RuntimeError("inatteignable")  # pragma: no cover


async def orient_candidates(
    client: httpx.AsyncClient, candidates: Sequence[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[tuple[str, int]], list[tuple[int, int]]]:
    """Oriente les candidats et écarte ceux qui ne sont pas au bord de la mer.

    Renvoie `(candidats côtiers, clés OSM écartées, tuiles abandonnées)`.

    Les clés écartées ne le sont **que** sur la foi d'un trait de côte
    réellement obtenu : une tuile abandonnée rend ses candidats tels quels,
    sans orientation et sans les marquer. C'est ce qui permet de supprimer en
    confiance les spots non côtiers à la passe suivante — un import dégradé ne
    doit jamais faire supprimer quoi que ce soit.
    """
    by_tile: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_tile[tile_of(candidate["lat"], candidate["lon"])].append(candidate)

    coastal: list[dict[str, Any]] = []
    dropped_keys: list[tuple[str, int]] = []
    abandoned: list[tuple[int, int]] = []

    for index, (tile, tile_candidates) in enumerate(sorted(by_tile.items()), start=1):
        try:
            ways = await fetch_coastline(client, tile)
        except Exception as exc:
            # Tuile définitivement injoignable : on garde les candidats sans
            # orientation plutôt que de les perdre, et on la signale en fin de
            # run pour un rejeu ciblé.
            logger.error(
                "Tuile %s abandonnée après toutes les attentes : %s", tile, exc
            )
            abandoned.append(tile)
            coastal.extend(tile_candidates)
            continue

        kept = 0
        for candidate in tile_candidates:
            orientation = coast_orientation(
                candidate["lat"], candidate["lon"], ways
            )
            if orientation is None:
                dropped_keys.append((candidate["osm_type"], candidate["osm_id"]))
                continue
            candidate.update(orientation)
            coastal.append(candidate)
            kept += 1

        logger.info(
            "Tuile %d/%d %s : %d segments de côte, %d/%d candidats retenus",
            index,
            len(by_tile),
            tile,
            len(ways),
            kept,
            len(tile_candidates),
        )

    return coastal, dropped_keys, abandoned


# ── Passe 3 : écriture ─────────────────────────────────────────────────────


async def _existing_slugs(db: AsyncSession) -> set[str]:
    result = await db.execute(select(Spot.slug))
    return set(result.scalars().all())


def _allocate_slug(
    candidate: dict[str, Any], taken: set[str], current: Optional[str]
) -> str:
    """Slug stable pour un spot OSM.

    Un spot déjà importé garde son slug même si son nom change dans OSM : le
    slug est dans les URL et dans les favoris du téléphone, le renommer à
    chaque import casserait les liens pour rien.
    """
    if current:
        return current

    base = slugify(candidate["name"]) or f"spot-{candidate['osm_id']}"
    slug, suffix = base, 2
    while slug in taken:
        slug = f"{base[:55]}-{suffix}"
        suffix += 1
    taken.add(slug)
    return slug


async def upsert_spots(
    db: AsyncSession, candidates: Sequence[dict[str, Any]], dry_run: bool = False
) -> dict[str, int]:
    """Insère ou met à jour, sans jamais toucher aux spots `source='user'`."""
    stats = {"created": 0, "updated": 0, "skipped_user": 0}
    if not candidates:
        return stats

    result = await db.execute(
        select(Spot).where(
            Spot.osm_id.in_([candidate["osm_id"] for candidate in candidates])
        )
    )
    existing = {
        (spot.osm_type, spot.osm_id): spot
        for spot in result.scalars().all()
        if spot.osm_id is not None
    }

    taken = await _existing_slugs(db)

    for candidate in candidates:
        spot = existing.get((candidate["osm_type"], candidate["osm_id"]))

        if spot is not None and spot.source == SpotSource.USER.value:
            # Un spot ajouté à la main a pu être rattaché à un objet OSM ; il
            # reste la propriété de Jules, l'import ne le réécrit pas.
            stats["skipped_user"] += 1
            continue

        if spot is None:
            spot = Spot(
                slug=_allocate_slug(candidate, taken, None),
                osm_type=candidate["osm_type"],
                osm_id=candidate["osm_id"],
                source=SpotSource.OSM.value,
            )
            db.add(spot)
            stats["created"] += 1
        else:
            stats["updated"] += 1

        spot.name = candidate["name"]
        spot.lat = candidate["lat"]
        spot.lon = candidate["lon"]
        spot.country_code = candidate["country_code"] or spot.country_code
        spot.spot_type = candidate["spot_type"]
        spot.osm_tags = candidate["tags"]

        # L'orientation n'est écrasée que si l'import en a trouvé une : une
        # tuile Overpass en échec ne doit pas effacer un calcul réussi le mois
        # dernier.
        if candidate.get("onshore_dir_deg") is not None:
            spot.coast_bearing_deg = candidate["coast_bearing_deg"]
            spot.onshore_dir_deg = candidate["onshore_dir_deg"]
            spot.coast_distance_m = candidate["coast_distance_m"]

        # `tier` et `is_active` ne sont JAMAIS écrits ici : ils appartiennent à
        # `spot_tiers.recompute_tiers`, qui seul sait ce qui est en favori.

    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return stats


async def delete_inland_spots(
    db: AsyncSession,
    dropped_keys: Sequence[tuple[str, int]],
    dry_run: bool = False,
) -> int:
    """Supprime les spots OSM que le filtre côtier vient d'écarter.

    Sans ça, une plage de lac entrée pendant un passage dégradé — trait de côte
    indisponible, donc aucun filtre appliqué — resterait au catalogue pour
    toujours : les passes suivantes l'écartent bien de la liste des candidats,
    mais l'upsert ne touche que ce qu'on lui donne. Il faut donc une
    suppression explicite.

    Ne sont supprimés que les spots `source='osm'` : un spot ajouté à la main
    l'a été en connaissance de cause, et il n'est pas reconstituable.

    Deux exceptions, qui priment sur le verdict du trait de côte :
    - un spot où Jules a déjà surfé est un spot, quoi qu'en dise OSM (et la
      clé étrangère `RESTRICT` de `surf_sessions` ferait de toute façon
      échouer la suppression) ;
    - un spot en favori ou masqué est référencé par un identifiant dans
      `spot_preferences`, qui n'a pas de clé étrangère pour le nettoyer : le
      supprimer laisserait un lien mort sur le téléphone.
    """
    if not dropped_keys:
        return 0

    result = await db.execute(
        select(Spot).where(
            Spot.source == SpotSource.OSM.value,
            Spot.osm_id.in_([osm_id for _, osm_id in dropped_keys]),
        )
    )
    wanted = set(dropped_keys)
    candidates = [
        spot
        for spot in result.scalars().all()
        if (spot.osm_type, spot.osm_id) in wanted
    ]
    if not candidates:
        return 0

    spot_ids = [spot.id for spot in candidates]

    surfed = set(
        (
            await db.execute(
                select(SurfSession.spot_id).where(SurfSession.spot_id.in_(spot_ids))
            )
        )
        .scalars()
        .all()
    )

    referenced: set[int] = set()
    for preferences in (
        (await db.execute(select(SpotPreference))).scalars().all()
    ):
        referenced |= {int(i) for i in (preferences.favorite_spot_ids or [])}
        referenced |= {int(i) for i in (preferences.hidden_spot_ids or [])}

    deleted = 0
    for spot in candidates:
        if spot.id in surfed:
            logger.info(
                "Spot %s gardé malgré le filtre côtier : des sessions y sont "
                "enregistrées",
                spot.slug,
            )
            continue
        if spot.id in referenced:
            logger.info(
                "Spot %s gardé malgré le filtre côtier : il est en favori ou "
                "masqué",
                spot.slug,
            )
            continue
        logger.info(
            "Suppression de %s (%s) : pas de mer à moins de %d m",
            spot.slug,
            spot.name,
            int(MAX_COAST_DISTANCE_M),
        )
        await db.delete(spot)
        deleted += 1

    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return deleted


# ── Orchestration ──────────────────────────────────────────────────────────


async def run(
    bbox: Optional[str] = None,
    skip_coastline: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(OVERPASS_TIMEOUT_S + 30)
    ) as client:
        logger.info("Overpass : candidats %s", bbox or "(monde entier)")
        payload = await overpass(client, spots_query(bbox))
        candidates = parse_elements(payload)
        logger.info("%d candidats nommés", len(candidates))

        dropped_keys: list[tuple[str, int]] = []
        abandoned: list[tuple[int, int]] = []
        if not skip_coastline:
            candidates, dropped_keys, abandoned = await orient_candidates(
                client, candidates
            )
            logger.info(
                "%d spots côtiers retenus, %d écartés (pas de mer à moins de %d m)",
                len(candidates),
                len(dropped_keys),
                int(MAX_COAST_DISTANCE_M),
            )

        async with async_session() as db:
            stats = await upsert_spots(db, candidates, dry_run)
            stats["deleted_inland"] = await delete_inland_spots(
                db, dropped_keys, dry_run
            )

        stats["dropped_inland"] = len(dropped_keys)
        stats["abandoned_tiles"] = len(abandoned)

        logger.info(
            "Spots : %d créés, %d mis à jour, %d supprimés (non côtiers), "
            "%d ignorés (source=user)",
            stats["created"],
            stats["updated"],
            stats["deleted_inland"],
            stats["skipped_user"],
        )

        if abandoned:
            logger.warning(
                "%d tuile(s) abandonnée(s) : leurs spots sont restés sans "
                "orientation et n'ont PAS été filtrés. À rejouer :",
                len(abandoned),
            )
            for command in replay_commands(abandoned):
                logger.warning("    %s", command)

        return stats


def replay_commands(tiles: Sequence[tuple[int, int]]) -> list[str]:
    """Commandes `--bbox` prêtes à coller pour rattraper les tuiles perdues."""
    commands = []
    for tile in tiles:
        min_lat, min_lon, max_lat, max_lon = tile_bbox(tile)
        commands.append(
            "python -m scripts.import_osm_spots --bbox "
            f"{min_lat:.2f},{min_lon:.2f},{max_lat:.2f},{max_lon:.2f}"
        )
    return commands


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bbox",
        help="Limite la requête : min_lat,min_lon,max_lat,max_lon (pour tester)",
    )
    parser.add_argument(
        "--skip-coastline",
        action="store_true",
        help=(
            "N'interroge pas le trait de côte : ni orientation, ni filtre "
            "côtier. À réserver aux essais — le catalogue se remplira de plages "
            "de lac."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Interroge Overpass et journalise, sans rien écrire en base",
    )
    args = parser.parse_args(argv)

    asyncio.run(
        run(bbox=args.bbox, skip_coastline=args.skip_coastline, dry_run=args.dry_run)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
