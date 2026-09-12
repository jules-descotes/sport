"""Import OSM sur un extrait figé, Overpass mocké.

Quatre propriétés à tenir :

1. **Ce sont des spots, pas des magasins.** Relevé sur le terrain : les 68
   objets `sport=surfing` de la côte basco-landaise sont tous des commerces,
   des écoles ou des clubs. Les vrais spots sont dans les `natural=beach`
   nommées. Le filtre n'est donc pas un détail d'hygiène, c'est ce qui décide
   si le catalogue sert à quelque chose.
2. **Idempotence** — le script tourne tous les mois ; deux passes de suite sur
   le même extrait doivent donner exactement le même catalogue.
3. **Les spots `source='user'` sont intouchables** — ils ont été ajoutés à la
   main là où OSM est vide, et c'est la seule donnée qui ne se reconstitue pas.
4. **Pas de mer, pas de spot** — une plage de lac est écartée, pas importée
   sans orientation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.enums import SpotSource, SpotTier, SpotType
from app.models.spot import Spot
from scripts.import_osm_spots import (
    coast_orientation,
    is_business,
    parse_coastlines,
    parse_elements,
    tile_of,
    upsert_spots,
)

# Extrait figé, calqué sur ce que rend vraiment Overpass sur cette côte.
OVERPASS_SPOTS = {
    "version": 0.6,
    "elements": [
        # Une plage nommée : le cas courant, et le seul qui donne de vrais spots.
        {
            "type": "node",
            "id": 1_234_567_890_123,
            "lat": 43.6640,
            "lon": -1.4400,
            "tags": {
                "natural": "beach",
                "name": "Plage de la Gravière",
                "surface": "sand",
                "is_in:country_code": "FR",
            },
        },
        # Une zone : Overpass en donne le centroïde avec `out center`.
        {
            "type": "way",
            "id": 98_765_432,
            "center": {"lat": 43.4820, "lon": -1.5610},
            "tags": {"natural": "beach", "name": "Côte des Basques"},
        },
        # Un pic nommé en `sport=surfing`, sans étiquette de commerce.
        {
            "type": "relation",
            "id": 55_555,
            "center": {"lat": 43.5400, "lon": -1.5200},
            "tags": {"sport": "surfing", "name": "Parlementia", "natural": "reef"},
        },
        # ── Ce qui doit être écarté ──────────────────────────────────────
        {
            "type": "node",
            "id": 11,
            "lat": 43.66,
            "lon": -1.43,
            "tags": {"sport": "surfing", "shop": "sports", "name": "Rip Curl"},
        },
        {
            "type": "node",
            "id": 12,
            "lat": 43.66,
            "lon": -1.43,
            "tags": {"sport": "surfing", "club": "sport", "name": "Surf Academy"},
        },
        {
            "type": "node",
            "id": 13,
            "lat": 43.66,
            "lon": -1.43,
            "tags": {"sport": "surfing", "leisure": "sports_centre", "name": "École"},
        },
        # Sans nom : un spot qu'on ne peut pas choisir dans une liste.
        {
            "type": "node",
            "id": 42,
            "lat": 43.50,
            "lon": -1.55,
            "tags": {"natural": "beach"},
        },
        # Way sans centroïde : Overpass n'a pas résolu la géométrie.
        {"type": "way", "id": 43, "tags": {"natural": "beach", "name": "Sans géo"}},
    ],
}

# Trait de côte landais : nord → sud, terre à gauche (à l'est).
OVERPASS_COASTLINE = {
    "version": 0.6,
    "elements": [
        {
            "type": "way",
            "id": 777,
            "tags": {"natural": "coastline"},
            "geometry": [
                {"lat": 43.70, "lon": -1.4390},
                {"lat": 43.68, "lon": -1.4392},
                {"lat": 43.66, "lon": -1.4394},
                {"lat": 43.64, "lon": -1.4396},
            ],
        },
        # Une ligne trop courte pour être une polyligne : elle doit être ignorée.
        {"type": "way", "id": 778, "geometry": [{"lat": 43.6, "lon": -1.4}]},
    ],
}


# ── Filtrage du commerce ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tags",
    [
        {"sport": "surfing", "shop": "sports"},
        {"sport": "surfing", "club": "sport"},
        {"sport": "surfing", "amenity": "cafe"},
        {"sport": "surfing", "leisure": "sports_centre"},
        {"sport": "surfing", "tourism": "hostel"},
        {"sport": "surfing", "building": "yes"},
    ],
)
def test_businesses_are_rejected(tags: dict[str, str]) -> None:
    """`sport=surfing` désigne surtout des magasins : sans ce filtre, le
    catalogue est un annuaire de shops."""
    assert is_business(tags) is True


@pytest.mark.parametrize(
    "tags",
    [
        {"sport": "surfing"},
        {"natural": "beach", "name": "Plage de la Gravière"},
        {"natural": "reef", "name": "Parlementia"},
    ],
)
def test_real_spots_are_kept(tags: dict[str, str]) -> None:
    assert is_business(tags) is False


def test_parse_elements_drops_shops_clubs_and_schools() -> None:
    candidates = parse_elements(OVERPASS_SPOTS)

    assert [c["name"] for c in candidates] == [
        "Plage de la Gravière",
        "Côte des Basques",
        "Parlementia",
    ]


def test_parse_elements_keeps_nodes_ways_and_relations() -> None:
    """Un `way` ou une `relation` n'a pas de coordonnée propre : c'est le
    centroïde d'`out center` qui sert."""
    assert {c["osm_type"] for c in parse_elements(OVERPASS_SPOTS)} == {
        "node",
        "way",
        "relation",
    }


def test_parse_elements_drops_unnamed_and_ungeolocated_objects() -> None:
    assert len(parse_elements(OVERPASS_SPOTS)) == 3


def test_spot_type_is_read_from_the_tags() -> None:
    by_name = {c["name"]: c for c in parse_elements(OVERPASS_SPOTS)}

    assert by_name["Plage de la Gravière"]["spot_type"] == SpotType.BEACH.value
    assert by_name["Plage de la Gravière"]["country_code"] == "FR"
    assert by_name["Parlementia"]["spot_type"] == SpotType.REEF.value
    # Pas de pays dans les tags : on ne l'invente pas.
    assert by_name["Côte des Basques"]["country_code"] is None


def test_big_osm_ids_survive() -> None:
    """Les identifiants de nœuds OSM ont dépassé 2^31 depuis longtemps."""
    assert any(c["osm_id"] > 2**31 for c in parse_elements(OVERPASS_SPOTS))


# ── Orientation de côte et filtre côtier ───────────────────────────────────


def test_parse_coastlines_drops_degenerate_ways() -> None:
    ways = parse_coastlines(OVERPASS_COASTLINE)
    assert len(ways) == 1
    assert len(ways[0]) == 4


def test_coast_orientation_faces_the_sea() -> None:
    """Trait de côte nord-sud, terre à l'est : la plage regarde plein ouest."""
    orientation = coast_orientation(43.6640, -1.4450, parse_coastlines(OVERPASS_COASTLINE))

    assert orientation is not None
    assert orientation["coast_bearing_deg"] == pytest.approx(180.0, abs=1.0)
    assert orientation["onshore_dir_deg"] == pytest.approx(270.0, abs=1.0)
    assert orientation["coast_distance_m"] < 1000.0


def test_inland_candidate_is_rejected_outright() -> None:
    """Plage de lac ou vague de rivière : ce n'est pas un spot de surf.

    On l'écarte, on ne l'importe pas « sans orientation » — sinon le catalogue
    mondial se remplit de plans d'eau.
    """
    assert coast_orientation(45.76, 4.83, parse_coastlines(OVERPASS_COASTLINE)) is None


def test_tiles_group_nearby_candidates_together() -> None:
    """Le trait de côte est demandé par tuile, pas candidat par candidat."""
    assert tile_of(43.664, -1.440) == tile_of(43.680, -1.430)
    assert tile_of(43.664, -1.440) != tile_of(49.340, -0.500)


# ── Upsert ─────────────────────────────────────────────────────────────────


async def test_import_creates_spots(db_session) -> None:
    stats = await upsert_spots(db_session, parse_elements(OVERPASS_SPOTS))

    assert stats == {"created": 3, "updated": 0, "skipped_user": 0}

    spots = (await db_session.execute(select(Spot).order_by(Spot.slug))).scalars().all()
    assert [spot.slug for spot in spots] == [
        "cote-des-basques",
        "parlementia",
        "plage-de-la-graviere",
    ]
    assert all(spot.source == SpotSource.OSM.value for spot in spots)
    # L'import ne décide jamais de ce qui est ingéré.
    assert all(spot.tier == SpotTier.CATALOG.value for spot in spots)
    assert all(spot.is_active is False for spot in spots)


async def test_import_is_idempotent(db_session) -> None:
    """Deux passes de suite sur le même extrait : le catalogue ne bouge pas."""
    candidates = parse_elements(OVERPASS_SPOTS)

    await upsert_spots(db_session, candidates)
    first = (
        await db_session.execute(select(func.count()).select_from(Spot))
    ).scalar_one()

    stats = await upsert_spots(db_session, candidates)
    second = (
        await db_session.execute(select(func.count()).select_from(Spot))
    ).scalar_one()

    assert first == second == 3
    assert stats == {"created": 0, "updated": 3, "skipped_user": 0}


async def test_import_writes_the_computed_orientation(db_session) -> None:
    candidates = parse_elements(OVERPASS_SPOTS)
    ways = parse_coastlines(OVERPASS_COASTLINE)
    candidates[0].update(coast_orientation(43.6640, -1.4450, ways))

    await upsert_spots(db_session, candidates)

    spot = (
        await db_session.execute(
            select(Spot).where(Spot.slug == "plage-de-la-graviere")
        )
    ).scalar_one()
    assert spot.onshore_dir_deg == pytest.approx(270.0, abs=1.0)


async def test_a_failed_coastline_tile_does_not_erase_a_known_orientation(
    db_session,
) -> None:
    """Une tuile Overpass en échec ne doit pas effacer le calcul du mois dernier."""
    candidates = parse_elements(OVERPASS_SPOTS)
    candidates[0].update(coast_orientation(43.6640, -1.4450, parse_coastlines(OVERPASS_COASTLINE)))
    await upsert_spots(db_session, candidates)

    # Deuxième passe, orientation absente (tuile injoignable).
    await upsert_spots(db_session, parse_elements(OVERPASS_SPOTS))

    spot = (
        await db_session.execute(
            select(Spot).where(Spot.slug == "plage-de-la-graviere")
        )
    ).scalar_one()
    assert spot.onshore_dir_deg == pytest.approx(270.0, abs=1.0)


async def test_import_updates_a_renamed_spot_but_keeps_its_slug(db_session) -> None:
    """Le slug est dans les URL et dans les favoris : il ne bouge jamais."""
    await upsert_spots(db_session, parse_elements(OVERPASS_SPOTS))

    renamed = parse_elements(OVERPASS_SPOTS)
    renamed[0]["name"] = "Plage de la Gravière (nord)"
    renamed[0]["lat"] = 43.6650
    await upsert_spots(db_session, renamed)

    spot = (
        await db_session.execute(
            select(Spot).where(Spot.slug == "plage-de-la-graviere")
        )
    ).scalar_one()
    assert spot.name == "Plage de la Gravière (nord)"
    assert spot.lat == pytest.approx(43.6650)


async def test_import_never_touches_user_spots(db_session, make_spot) -> None:
    """Un spot ajouté à la main reste la propriété de Jules, quoi qu'il arrive."""
    mine = await make_spot(
        name="Le pic secret",
        slug="le-pic-secret",
        source=SpotSource.USER.value,
        tier=SpotTier.HOME.value,
    )
    # On lui rattache après coup l'objet OSM que l'import va rapporter.
    mine.osm_type = "node"
    mine.osm_id = 1_234_567_890_123
    await db_session.commit()

    stats = await upsert_spots(db_session, parse_elements(OVERPASS_SPOTS))

    assert stats["skipped_user"] == 1
    await db_session.refresh(mine)
    assert mine.name == "Le pic secret"
    assert mine.tier == SpotTier.HOME.value


async def test_duplicate_names_get_distinct_slugs(db_session) -> None:
    """Il y a plusieurs « Grande Plage » dans le monde : le suffixe est la règle."""
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 10,
                "lat": 43.0,
                "lon": -1.0,
                "tags": {"natural": "beach", "name": "Grande Plage"},
            },
            {
                "type": "node",
                "id": 11,
                "lat": 44.0,
                "lon": -1.0,
                "tags": {"natural": "beach", "name": "Grande Plage"},
            },
        ]
    }
    await upsert_spots(db_session, parse_elements(payload))

    slugs = sorted((await db_session.execute(select(Spot.slug))).scalars().all())
    assert slugs == ["grande-plage", "grande-plage-2"]


async def test_dry_run_writes_nothing(db_session) -> None:
    await upsert_spots(db_session, parse_elements(OVERPASS_SPOTS), dry_run=True)

    count = (
        await db_session.execute(select(func.count()).select_from(Spot))
    ).scalar_one()
    assert count == 0
