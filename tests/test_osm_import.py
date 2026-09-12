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

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from app.models.enums import SpotSource, SpotTier, SpotType
from app.models.spot import Spot
from app.models.surf_session import SurfSession
from scripts.import_osm_spots import (
    coast_orientation,
    delete_inland_spots,
    is_business,
    orient_candidates,
    parse_coastlines,
    parse_elements,
    replay_commands,
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


# ── Nettoyage des spots non côtiers ────────────────────────────────────────
#
# Un passage dégradé — trait de côte indisponible — importe les candidats sans
# les filtrer. Les passes suivantes les écartent bien de la liste, mais l'upsert
# ne touche que ce qu'on lui donne : sans suppression explicite, la plage de lac
# reste au catalogue pour toujours.


async def test_inland_osm_spot_is_deleted_on_replay(db_session, make_spot) -> None:
    lake = await make_spot(
        name="Plage du lac", slug="plage-du-lac", lat=45.76, lon=4.83,
        osm_type="node", osm_id=999,
    )

    deleted = await delete_inland_spots(db_session, [("node", 999)])

    assert deleted == 1
    assert (
        await db_session.execute(select(Spot).where(Spot.id == lake.id))
    ).scalar_one_or_none() is None


async def test_replay_is_idempotent_once_the_spot_is_gone(db_session) -> None:
    assert await delete_inland_spots(db_session, [("node", 999)]) == 0


async def test_user_spots_are_never_deleted(db_session, make_spot) -> None:
    """Un spot ajouté à la main l'a été en connaissance de cause."""
    mine = await make_spot(
        name="Vague de rivière", slug="vague-de-riviere", lat=45.76, lon=4.83,
        source=SpotSource.USER.value,
    )
    mine.osm_type = "node"
    mine.osm_id = 999
    await db_session.commit()

    deleted = await delete_inland_spots(db_session, [("node", 999)])

    assert deleted == 0
    await db_session.refresh(mine)
    assert mine.slug == "vague-de-riviere"


async def test_a_surfed_spot_survives_the_coastal_filter(
    db_session, user, make_spot
) -> None:
    """Si Jules y a surfé, c'est un spot — quoi qu'en dise le trait de côte."""
    spot = await make_spot(
        name="Pic douteux", slug="pic-douteux", lat=45.76, lon=4.83,
        osm_type="node", osm_id=999,
    )
    db_session.add(
        SurfSession(
            user_id=user.id,
            spot_id=spot.id,
            started_at=datetime(2026, 3, 4, 9, tzinfo=UTC),
            discipline="surf",
        )
    )
    await db_session.commit()

    deleted = await delete_inland_spots(db_session, [("node", 999)])

    assert deleted == 0
    await db_session.refresh(spot)
    assert spot.slug == "pic-douteux"


async def test_a_favourite_spot_survives_the_coastal_filter(
    db_session, preferences, make_spot
) -> None:
    """`spot_preferences` n'a pas de clé étrangère pour nettoyer l'identifiant :
    supprimer laisserait un lien mort sur le téléphone."""
    spot = await make_spot(
        name="Pic douteux", slug="pic-douteux", lat=45.76, lon=4.83,
        osm_type="node", osm_id=999,
    )
    preferences.favorite_spot_ids = [spot.id]
    await db_session.commit()

    assert await delete_inland_spots(db_session, [("node", 999)]) == 0


async def test_only_the_dropped_keys_are_deleted(db_session, make_spot) -> None:
    """La suppression est ciblée : un spot côtier voisin n'est pas emporté."""
    lake = await make_spot(
        name="Plage du lac", slug="plage-du-lac", lat=45.76, lon=4.83,
        osm_type="node", osm_id=999,
    )
    keeper = await make_spot(
        name="La Gravière", slug="la-graviere", osm_type="node", osm_id=1000,
    )

    await delete_inland_spots(db_session, [("node", 999)])

    remaining = (await db_session.execute(select(Spot.slug))).scalars().all()
    assert remaining == ["la-graviere"]
    assert keeper.id is not None and lake is not None


async def test_dry_run_deletes_nothing(db_session, make_spot) -> None:
    await make_spot(
        name="Plage du lac", slug="plage-du-lac", lat=45.76, lon=4.83,
        osm_type="node", osm_id=999,
    )

    deleted = await delete_inland_spots(db_session, [("node", 999)], dry_run=True)

    assert deleted == 1
    count = (
        await db_session.execute(select(func.count()).select_from(Spot))
    ).scalar_one()
    assert count == 1


# ── Ce qui rend la suppression sûre : le passage dégradé ───────────────────


async def test_an_abandoned_tile_drops_nothing(monkeypatch) -> None:
    """Une tuile perdue rend ses candidats tels quels, sans les marquer.

    C'est la garantie qui autorise la suppression : un import dégradé ne doit
    jamais faire disparaître un spot du catalogue.
    """
    import scripts.import_osm_spots as module

    async def _blocked(client, query):
        raise httpx.ConnectError("All connection attempts failed")

    slept: list[float] = []

    async def _no_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(module, "overpass", _blocked)
    monkeypatch.setattr(module.asyncio, "sleep", _no_sleep)

    candidates = parse_elements(OVERPASS_SPOTS)
    coastal, dropped_keys, abandoned = await orient_candidates(None, candidates)

    assert dropped_keys == []
    assert len(coastal) == len(candidates)
    assert len(abandoned) == 3
    # Trois tuiles, chacune réessayée après 60 s, 120 s puis 300 s.
    assert slept == list(module.BLOCKED_BACKOFF_S) * 3


async def test_a_blocked_tile_is_retried_and_then_succeeds(monkeypatch) -> None:
    """Overpass qui refuse la connexion n'est pas une raison d'abandonner."""
    import scripts.import_osm_spots as module

    attempts = {"count": 0}

    async def _flaky(client, query):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("All connection attempts failed")
        return OVERPASS_COASTLINE

    async def _no_sleep(seconds):
        return None

    monkeypatch.setattr(module, "overpass", _flaky)
    monkeypatch.setattr(module.asyncio, "sleep", _no_sleep)

    ways = await module.fetch_coastline(None, tile_of(43.664, -1.44))

    assert attempts["count"] == 2
    assert len(ways) == 1


async def test_a_malformed_query_is_not_retried_for_eight_minutes(
    monkeypatch,
) -> None:
    """Une requête fautive n'a aucune raison d'être rejouée après 300 s."""
    import scripts.import_osm_spots as module

    attempts = {"count": 0}
    request = httpx.Request("POST", "https://overpass.invalid")

    async def _bad_request(client, query):
        attempts["count"] += 1
        raise httpx.HTTPStatusError(
            "400", request=request, response=httpx.Response(400, request=request)
        )

    monkeypatch.setattr(module, "overpass", _bad_request)

    with pytest.raises(httpx.HTTPStatusError):
        await module.fetch_coastline(None, tile_of(43.664, -1.44))

    assert attempts["count"] == 1


def test_abandoned_tiles_come_with_a_replay_command() -> None:
    commands = replay_commands([tile_of(43.664, -1.44)])

    assert commands == [
        "python -m scripts.import_osm_spots --bbox 43.35,-1.65,44.15,-0.85"
    ]


async def test_requests_are_spaced_by_at_least_two_seconds(monkeypatch) -> None:
    """Enchaîner les requêtes est exactement ce qui déclenche le blocage."""
    import scripts.import_osm_spots as module

    slept: list[float] = []

    async def _no_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(module.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(module, "_last_request_at", None)

    await module._throttle()
    await module._throttle()

    # La première requête part tout de suite, la seconde attend la pause.
    assert len(slept) == 1
    assert slept[0] == pytest.approx(module.PAUSE_BETWEEN_QUERIES_S, abs=0.1)
