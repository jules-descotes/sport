"""Spot favori — une seule prévision par défaut, et un seul chemin d'ingestion.

Décidé le 12/09 au soir (cf. PROJET.md §11) : l'écran Jour montre la prévision
du spot favori du profil, et **rien d'autre ne s'ingère tant qu'on ne le
regarde pas**. Ces tests tiennent les deux moitiés de cette phrase :

- le niveau `home` — le seul que le job planifié interroge — part du favori ;
- aucun chemin n'interroge Open-Meteo pour un spot `potential` qu'on n'a pas
  ouvert : ni l'ouverture de l'app, ni la recherche, ni la liste des favoris.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.enums import SpotTier
from app.models.spot import Spot
from app.services.spot_tiers import get_or_create_preferences, recompute_tiers
from tests.conftest import HOSSEGOR_LAT, HOSSEGOR_LON


@pytest.fixture
def spy_refresh(monkeypatch):
    """Espionne l'unique porte de sortie vers Open-Meteo.

    Tout appel réel passe par `refresh_spot_ids_detached` : ce qui n'est pas
    dans cette liste n'a jamais été ingéré.
    """
    from app.services import forecast_ingest

    touched: list[int] = []

    async def _record(spot_ids):
        touched.extend(spot_ids)
        return len(list(spot_ids))

    monkeypatch.setattr(forecast_ingest, "refresh_spot_ids_detached", _record)
    return touched


async def _set_favorite(auth_client, spot: Spot) -> None:
    response = await auth_client.put(
        "/api/v1/auth/me/profile", json={"home_spot_id": spot.id}
    )
    assert response.status_code == 200


# ── Le niveau `home` part du favori ────────────────────────────────────────


async def test_favorite_spot_becomes_home_tier(
    auth_client, db_session, make_spot
) -> None:
    """Mettre un favori, c'est décider de ce que le job planifié interroge."""
    spot = await make_spot(tier=SpotTier.POTENTIAL.value)

    await _set_favorite(auth_client, spot)

    await db_session.refresh(spot)
    assert spot.tier == SpotTier.HOME.value
    assert spot.is_active is True


async def test_changing_the_favorite_demotes_the_previous_one(
    auth_client, db_session, make_spot
) -> None:
    """Le job ne doit pas continuer d'interroger un spot qu'on ne regarde plus."""
    first = await make_spot(name="Premier", slug="premier")
    second = await make_spot(name="Second", slug="second", lat=HOSSEGOR_LAT + 0.05)

    await _set_favorite(auth_client, first)
    await _set_favorite(auth_client, second)

    await db_session.refresh(first)
    await db_session.refresh(second)
    assert second.tier == SpotTier.HOME.value
    assert first.tier != SpotTier.HOME.value


async def test_favorite_survives_a_tier_recomputation(
    auth_client, db_session, user, make_spot
) -> None:
    """Un favori hors du rayon reste maison : c'est lui qu'on regarde tous les matins."""
    far = await make_spot(name="Loin", slug="loin", lat=HOSSEGOR_LAT + 3.0)

    await _set_favorite(auth_client, far)

    # Le recalcul tourne à chaque connexion : il ne doit pas déclasser le favori
    # sous prétexte qu'il est à trois cents kilomètres.
    preferences = await get_or_create_preferences(db_session, user.id)
    await recompute_tiers(db_session, preferences)

    await db_session.refresh(far)
    assert far.tier == SpotTier.HOME.value


async def test_unknown_favorite_is_rejected(auth_client) -> None:
    response = await auth_client.put(
        "/api/v1/auth/me/profile", json={"home_spot_id": 9999}
    )

    assert response.status_code == 404


# ── Rien ne s'ingère sans qu'on l'ait regardé ──────────────────────────────


async def test_recommend_only_ingests_the_favorite(
    auth_client, db_session, make_spot, spy_refresh
) -> None:
    """Ouvrir l'app n'interroge pas le rayon : un spot, et c'est le favori."""
    favorite = await make_spot(name="Favori", slug="favori")
    await make_spot(
        name="Voisin", slug="voisin", lat=HOSSEGOR_LAT + 0.02,
        tier=SpotTier.POTENTIAL.value,
    )
    await make_spot(
        name="Autre", slug="autre", lat=HOSSEGOR_LAT + 0.03,
        tier=SpotTier.POTENTIAL.value,
    )
    await _set_favorite(auth_client, favorite)

    response = await auth_client.get(
        "/api/v1/recommend", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )

    assert response.status_code == 200
    assert spy_refresh == [favorite.id]
    assert response.json()["home_spot"]["slug"] == "favori"


async def test_recommend_without_a_favorite_ingests_nothing(
    auth_client, make_spot, spy_refresh
) -> None:
    """Tant qu'aucun favori n'est choisi, zéro appel — l'écran Jour le dira."""
    await make_spot(tier=SpotTier.POTENTIAL.value)

    response = await auth_client.get(
        "/api/v1/recommend", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )

    assert response.status_code == 200
    assert spy_refresh == []
    assert response.json()["home_spot"] is None


async def test_recommend_serves_the_favorite_without_a_position(
    auth_client, db_session, make_spot, make_forecast, spy_refresh
) -> None:
    """Géoloc refusée et pas de domicile : le favori suffit à remplir l'écran."""
    favorite = await make_spot()
    await make_forecast(favorite, fetched_at=datetime.now(UTC))
    await _set_favorite(auth_client, favorite)

    response = await auth_client.get("/api/v1/recommend")

    assert response.status_code == 200
    body = response.json()
    assert body["position_source"] == "spot"
    assert body["spots"][0]["slots"]


async def test_search_never_ingests(auth_client, make_spot, spy_refresh) -> None:
    """Chercher « Lafitenia » ne doit pas coûter trois appels Open-Meteo."""
    await make_spot(name="Lafitenia", slug="lafitenia", tier=SpotTier.POTENTIAL.value)

    response = await auth_client.get("/api/v1/spots/search", params={"q": "lafi"})

    assert response.status_code == 200
    assert [hit["slug"] for hit in response.json()] == ["lafitenia"]
    assert spy_refresh == []


async def test_nearby_never_ingests(auth_client, make_spot, spy_refresh) -> None:
    await make_spot(tier=SpotTier.POTENTIAL.value)

    response = await auth_client.get(
        "/api/v1/spots/nearby",
        params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON, "radius_km": 40},
    )

    assert response.status_code == 200
    assert spy_refresh == []


async def test_opening_a_spot_is_the_one_path_that_ingests(
    auth_client, make_spot, spy_refresh
) -> None:
    """Regarder un spot, c'est le seul geste qui autorise un appel."""
    spot = await make_spot(name="Parlementia", slug="parlementia")

    response = await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")

    assert response.status_code == 200
    assert spy_refresh == [spot.id]


# ── Sélecteur de l'écran Mer ───────────────────────────────────────────────


async def test_search_matches_anywhere_but_ranks_prefixes_first(
    auth_client, make_spot
) -> None:
    await make_spot(name="Plage de la Gravière", slug="graviere")
    await make_spot(name="Gravière Nord", slug="graviere-nord", lat=HOSSEGOR_LAT + 0.01)

    response = await auth_client.get(
        "/api/v1/spots/search", params={"q": "gravi"}
    )

    assert [hit["slug"] for hit in response.json()] == [
        "graviere-nord",
        "graviere",
    ]


async def test_search_needs_two_characters(auth_client) -> None:
    """Une lettre renverrait la moitié du catalogue mondial."""
    response = await auth_client.get("/api/v1/spots/search", params={"q": "a"})

    assert response.status_code == 422


async def test_favorites_list_puts_the_profile_spot_first(
    auth_client, make_spot
) -> None:
    secondary = await make_spot(name="Second", slug="second")
    favorite = await make_spot(
        name="Favori", slug="favori", lat=HOSSEGOR_LAT + 0.01
    )

    await auth_client.post(
        f"/api/v1/spots/{secondary.slug}/favorite", json={"favorite": True}
    )
    await _set_favorite(auth_client, favorite)

    response = await auth_client.get("/api/v1/spots/favorites")

    hits = response.json()
    assert [hit["slug"] for hit in hits] == ["favori", "second"]
    assert hits[0]["is_home"] is True
    assert hits[1]["is_home"] is False


async def test_favorites_list_is_empty_before_any_choice(auth_client) -> None:
    response = await auth_client.get("/api/v1/spots/favorites")

    assert response.json() == []


async def test_search_route_is_declared_before_the_parameterised_one(
    auth_client,
) -> None:
    """`/spots/search` doit être déclaré avant `/spots/{ref}`, sinon 422 (CLAUDE.md)."""
    response = await auth_client.get("/api/v1/spots/search", params={"q": "zz"})

    assert response.status_code == 200


# ── Grille de l'écran Mer ──────────────────────────────────────────────────


async def test_step_hours_thins_the_grid_without_changing_the_scores(
    auth_client, make_spot, make_forecast
) -> None:
    """Quarante points au lieu de cent vingt, mêmes notes : la marée reste lue
    sur toutes les heures, sinon les extrêmes du jour sont introuvables."""
    spot = await make_spot()
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    await make_forecast(spot, start=start, hours=48, fetched_at=datetime.now(UTC))

    full = (await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")).json()
    thin = (
        await auth_client.get(
            f"/api/v1/spots/{spot.slug}/forecast", params={"step_hours": 3}
        )
    ).json()

    assert len(thin["points"]) < len(full["points"])
    assert all(
        datetime.fromisoformat(point["ts"]).hour % 3 == 0
        for point in thin["points"]
    )

    by_ts = {point["ts"]: point for point in full["points"]}
    assert all(
        by_ts[point["ts"]]["score"] == point["score"] for point in thin["points"]
    )


async def test_forecast_point_says_whether_the_wind_is_offshore(
    auth_client, make_spot, make_forecast
) -> None:
    """L'écran ne connaît pas l'orientation de la côte : le back tranche terre / mer."""
    spot = await make_spot(onshore_dir_deg=270.0)  # plage plein ouest
    await make_forecast(
        spot, wind_direction_deg=90.0, wind_speed_kt=10.0,
        fetched_at=datetime.now(UTC),
    )

    body = (await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")).json()

    # Vent d'est sur une côte ouest : de terre, donc composante positive.
    assert body["points"][0]["wind_offshore_kt"] == pytest.approx(10.0, abs=0.1)


async def test_forecast_point_has_no_offshore_without_coast_orientation(
    auth_client, make_spot, make_forecast
) -> None:
    """Sans orientation connue, on ne devine pas — on se tait."""
    spot = await make_spot(onshore_dir_deg=None)
    await make_forecast(spot, fetched_at=datetime.now(UTC))

    body = (await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")).json()

    assert body["points"][0]["wind_offshore_kt"] is None
