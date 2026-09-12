"""API des spots : proximité, ajout manuel, favoris, masquage, prévision."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.enums import SpotSource, SpotTier
from app.models.spot import Spot
from app.services.spot_tiers import HOME_MAX
from tests.conftest import HOSSEGOR_LAT, HOSSEGOR_LON


async def test_nearby_requires_authentication(client, make_spot) -> None:
    await make_spot()
    response = await client.get(
        "/api/v1/spots/nearby", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )
    assert response.status_code == 401


async def test_nearby_sorts_by_distance(auth_client, make_spot) -> None:
    await make_spot(name="Loin", slug="loin", lat=HOSSEGOR_LAT + 0.20)
    await make_spot(name="Près", slug="pres", lat=HOSSEGOR_LAT + 0.01)

    response = await auth_client.get(
        "/api/v1/spots/nearby",
        params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON, "radius_km": 40},
    )

    assert response.status_code == 200
    body = response.json()
    assert [spot["slug"] for spot in body] == ["pres", "loin"]
    assert body[0]["distance_km"] < body[1]["distance_km"]


async def test_nearby_excludes_spots_outside_the_radius(auth_client, make_spot) -> None:
    await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)

    response = await auth_client.get(
        "/api/v1/spots/nearby",
        params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON, "radius_km": 40},
    )

    assert response.json() == []


async def test_nearby_returns_catalog_spots_too(auth_client, make_spot) -> None:
    """Un spot sans prévision reste un spot qu'on peut mettre en favori."""
    await make_spot(
        name="Catalogue", slug="catalogue", lat=HOSSEGOR_LAT + 0.01,
        tier=SpotTier.CATALOG.value,
    )

    response = await auth_client.get(
        "/api/v1/spots/nearby", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )

    assert [spot["slug"] for spot in response.json()] == ["catalogue"]


async def test_nearby_is_declared_before_the_parameterised_route(auth_client) -> None:
    """Sans cet ordre, FastAPI lit « nearby » comme un identifiant et renvoie 422."""
    response = await auth_client.get(
        "/api/v1/spots/nearby", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )
    assert response.status_code == 200


# ── Ajout manuel ───────────────────────────────────────────────────────────


async def test_create_spot_from_the_map(auth_client, db_session) -> None:
    """Là où OSM est vide, le spot s'ajoute en deux taps."""
    response = await auth_client.post(
        "/api/v1/spots",
        json={"name": "Le pic secret", "lat": 43.55, "lon": -1.45, "spot_type": "reef"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "le-pic-secret"
    assert body["source"] == SpotSource.USER.value

    spot = (
        await db_session.execute(select(Spot).where(Spot.slug == "le-pic-secret"))
    ).scalar_one()
    # Pas d'orientation : elle demande le trait de côte OSM, calculé par le
    # script d'import et par lui seul.
    assert spot.onshore_dir_deg is None


async def test_create_spot_rejects_an_unknown_type(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/spots",
        json={"name": "Bizarre", "lat": 43.5, "lon": -1.4, "spot_type": "volcan"},
    )
    assert response.status_code == 422


async def test_create_spot_disambiguates_duplicate_names(auth_client) -> None:
    payload = {"name": "Beach Break", "lat": 43.5, "lon": -1.4}
    first = await auth_client.post("/api/v1/spots", json=payload)
    second = await auth_client.post("/api/v1/spots", json=payload)

    assert first.json()["slug"] == "beach-break"
    assert second.json()["slug"] == "beach-break-2"


# ── Favoris et masquage ────────────────────────────────────────────────────


async def test_favorite_promotes_a_spot_to_home(
    auth_client, db_session, make_spot
) -> None:
    spot = await make_spot()

    response = await auth_client.post(
        f"/api/v1/spots/{spot.slug}/favorite", json={"favorite": True}
    )

    assert response.status_code == 200
    assert response.json()["favorite_spot_ids"] == [spot.id]

    await db_session.refresh(spot)
    assert spot.tier == SpotTier.HOME.value


async def test_unfavorite_demotes_the_spot(auth_client, db_session, make_spot) -> None:
    far = await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)
    await auth_client.post(f"/api/v1/spots/{far.id}/favorite", json={"favorite": True})

    await auth_client.post(f"/api/v1/spots/{far.id}/favorite", json={"favorite": False})

    await db_session.refresh(far)
    assert far.tier == SpotTier.CATALOG.value


async def test_favorites_are_capped_at_twenty(auth_client, make_spot) -> None:
    """Vingt favoris × 3 appels × 8 passes par jour : au-delà, le job n'a plus de sens."""
    for index in range(HOME_MAX):
        spot = await make_spot(
            name=f"Spot {index}", slug=f"spot-{index}", lat=39.0 + index / 100, lon=-9.0
        )
        response = await auth_client.post(
            f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
        )
        assert response.status_code == 200

    extra = await make_spot(name="Un de trop", slug="un-de-trop", lat=38.0, lon=-9.0)
    response = await auth_client.post(
        f"/api/v1/spots/{extra.id}/favorite", json={"favorite": True}
    )

    assert response.status_code == 409
    assert str(HOME_MAX) in response.json()["detail"]


async def test_favoriting_a_hidden_spot_unhides_it(auth_client, make_spot) -> None:
    """Garder les deux serait une contradiction sans issue à l'écran."""
    spot = await make_spot()
    await auth_client.post(f"/api/v1/spots/{spot.id}/hide", json={"hidden": True})

    response = await auth_client.post(
        f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
    )

    body = response.json()
    assert body["favorite_spot_ids"] == [spot.id]
    assert body["hidden_spot_ids"] == []


async def test_hidden_spot_disappears_from_nearby(auth_client, make_spot) -> None:
    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01)
    await auth_client.post(f"/api/v1/spots/{spot.id}/hide", json={"hidden": True})

    response = await auth_client.get(
        "/api/v1/spots/nearby", params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON}
    )

    assert response.json() == []


async def test_hidden_spot_can_be_listed_on_demand(auth_client, make_spot) -> None:
    """Il faut bien pouvoir le démasquer depuis le profil."""
    spot = await make_spot(lat=HOSSEGOR_LAT + 0.01)
    await auth_client.post(f"/api/v1/spots/{spot.id}/hide", json={"hidden": True})

    response = await auth_client.get(
        "/api/v1/spots/nearby",
        params={"lat": HOSSEGOR_LAT, "lon": HOSSEGOR_LON, "include_hidden": True},
    )

    assert [spot["slug"] for spot in response.json()] == [spot.slug]
    assert response.json()[0]["is_hidden"] is True


# ── Préférences ────────────────────────────────────────────────────────────


async def test_preferences_round_trip(auth_client) -> None:
    response = await auth_client.put(
        "/api/v1/spots/preferences",
        json={"radius_km": 25, "home_lat": HOSSEGOR_LAT, "home_lon": HOSSEGOR_LON},
    )

    assert response.status_code == 200
    assert response.json()["radius_km"] == 25

    read = await auth_client.get("/api/v1/spots/preferences")
    assert read.json()["home_lat"] == pytest.approx(HOSSEGOR_LAT)


async def test_changing_the_radius_recomputes_tiers(
    auth_client, db_session, make_spot
) -> None:
    spot = await make_spot(name="À 30 km", slug="a-30-km", lat=HOSSEGOR_LAT + 0.27)

    await auth_client.put(
        "/api/v1/spots/preferences",
        json={"radius_km": 10, "home_lat": HOSSEGOR_LAT, "home_lon": HOSSEGOR_LON},
    )
    await db_session.refresh(spot)
    assert spot.tier == SpotTier.CATALOG.value

    await auth_client.put("/api/v1/spots/preferences", json={"radius_km": 50})
    await db_session.refresh(spot)
    assert spot.tier == SpotTier.POTENTIAL.value


async def test_position_activates_nearby_spots(
    auth_client, db_session, make_spot
) -> None:
    away = await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)

    response = await auth_client.post(
        "/api/v1/spots/position", json={"lat": 39.61, "lon": -9.08}
    )

    assert response.status_code == 200
    await db_session.refresh(away)
    assert away.tier == SpotTier.POTENTIAL.value


# ── Prévision d'un spot ────────────────────────────────────────────────────


async def test_spot_forecast_is_scored(auth_client, make_spot, make_forecast) -> None:
    spot = await make_spot()
    await make_forecast(spot, fetched_at=datetime.now(UTC))

    response = await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")

    assert response.status_code == 200
    body = response.json()
    assert body["spot"]["slug"] == spot.slug
    assert body["refreshing"] is False
    assert body["points"]
    first = body["points"][0]
    assert 1.0 <= first["score"] <= 5.0
    assert 1 <= first["score_level"] <= 5
    assert first["sea_level_m"] is not None


async def test_spot_forecast_serves_the_cache_without_refetching(
    auth_client, make_spot, make_forecast, monkeypatch
) -> None:
    """Cache de moins de trois heures : zéro appel à Open-Meteo."""
    from app.services import forecast_ingest

    spot = await make_spot()
    await make_forecast(spot, fetched_at=datetime.now(UTC) - timedelta(hours=1))

    calls: list[list[int]] = []

    async def _never(spot_ids):
        calls.append(list(spot_ids))
        return 0

    monkeypatch.setattr(forecast_ingest, "refresh_spot_ids_detached", _never)

    response = await auth_client.get(f"/api/v1/spots/{spot.id}/forecast")

    assert response.status_code == 200
    assert calls == []


async def test_unknown_spot_returns_404(auth_client) -> None:
    assert (await auth_client.get("/api/v1/spots/pas-un-spot")).status_code == 404


async def test_spot_can_be_read_by_id_or_slug(auth_client, make_spot) -> None:
    """Le front navigue en slugs, les liens internes en identifiants."""
    spot = await make_spot()

    by_id = await auth_client.get(f"/api/v1/spots/{spot.id}")
    by_slug = await auth_client.get(f"/api/v1/spots/{spot.slug}")

    assert by_id.json() == by_slug.json()


async def test_webcam_url_can_be_attached(auth_client, make_spot) -> None:
    """On ne ré-héberge pas les flux : iframe ou lien sortant, rien d'autre."""
    spot = await make_spot()

    response = await auth_client.patch(
        f"/api/v1/spots/{spot.slug}",
        json={"webcam_url": "https://example.invalid/webcam"},
    )

    assert response.json()["webcam_url"] == "https://example.invalid/webcam"
