"""Les critères par l'API : saisie, ordre des favoris, et annonces sur Jour."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

PARLEMENTIA_RULES = {
    "wave_height_min_m": 0.5,
    "wave_height_max_m": 3.0,
    "wave_period_min_s": 10.0,
    "swell_sectors": ["O", "NO"],
    "wind_sectors": ["E", "SE"],
    "wind_max_kt": 15.0,
    "tide_phases": [],
    "hour_min": 6,
    "hour_max": 20,
}


async def test_a_spot_without_rules_reads_as_an_empty_set(
    auth_client, make_spot
) -> None:
    """Vide, et pas 404 : le formulaire s'ouvre pareil dans les deux cas."""
    spot = await make_spot()

    response = await auth_client.get(f"/api/v1/spots/{spot.id}/rules")

    assert response.status_code == 200
    body = response.json()
    assert body["spot_id"] == spot.id
    assert body["wave_height_max_m"] is None
    assert body["swell_sectors"] == []


async def test_rules_are_saved_and_read_back(auth_client, make_spot) -> None:
    spot = await make_spot()

    saved = await auth_client.put(
        f"/api/v1/spots/{spot.id}/rules", json=PARLEMENTIA_RULES
    )
    assert saved.status_code == 200
    assert saved.json()["swell_sectors"] == ["O", "NO"]

    read = await auth_client.get(f"/api/v1/spots/{spot.id}/rules")
    assert read.json()["wave_period_min_s"] == 10.0


async def test_a_full_send_can_erase_a_criterion(auth_client, make_spot) -> None:
    """C'est tout l'intérêt de l'envoi complet.

    Dans une mise à jour partielle, `null` voudrait dire à la fois « ne change
    pas » et « retire » — et on ne pourrait plus jamais revenir sur un seuil
    posé un soir.
    """
    spot = await make_spot()
    await auth_client.put(f"/api/v1/spots/{spot.id}/rules", json=PARLEMENTIA_RULES)

    cleared = await auth_client.put(
        f"/api/v1/spots/{spot.id}/rules",
        json={**PARLEMENTIA_RULES, "wave_height_max_m": None, "swell_sectors": []},
    )

    assert cleared.json()["wave_height_max_m"] is None
    assert cleared.json()["swell_sectors"] == []


async def test_an_unknown_sector_is_refused(auth_client, make_spot) -> None:
    """Un secteur mal orthographié ferait taire une règle en silence."""
    spot = await make_spot()

    response = await auth_client.put(
        f"/api/v1/spots/{spot.id}/rules",
        json={**PARLEMENTIA_RULES, "swell_sectors": ["OUEST"]},
    )

    assert response.status_code == 422


async def test_an_inverted_height_range_is_refused(auth_client, make_spot) -> None:
    spot = await make_spot()

    response = await auth_client.put(
        f"/api/v1/spots/{spot.id}/rules",
        json={
            **PARLEMENTIA_RULES,
            "wave_height_min_m": 3.0,
            "wave_height_max_m": 1.0,
        },
    )

    assert response.status_code == 422


async def test_rules_can_be_removed(auth_client, make_spot) -> None:
    spot = await make_spot()
    await auth_client.put(f"/api/v1/spots/{spot.id}/rules", json=PARLEMENTIA_RULES)

    removed = await auth_client.delete(f"/api/v1/spots/{spot.id}/rules")
    assert removed.status_code == 204

    assert (
        await auth_client.get(f"/api/v1/spots/{spot.id}/rules")
    ).json()["swell_sectors"] == []


# ── L'ordre des favoris ────────────────────────────────────────────────────


async def test_favorites_keep_the_order_they_are_given(
    auth_client, make_spot
) -> None:
    """L'ordre n'est pas cosmétique : c'est celui du sélecteur de l'écran Surf."""
    first = await make_spot(slug="a", name="A")
    second = await make_spot(slug="b", name="B")
    third = await make_spot(slug="c", name="C")

    for spot in (first, second, third):
        await auth_client.post(
            f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
        )

    reordered = await auth_client.put(
        "/api/v1/spots/favorites/order",
        json={"spot_ids": [third.id, first.id, second.id]},
    )

    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()] == [
        third.id,
        first.id,
        second.id,
    ]


async def test_a_partial_order_never_drops_a_favorite(
    auth_client, make_spot
) -> None:
    """Un ordre partiel n'est pas une suppression : on ne retire qu'en le disant."""
    first = await make_spot(slug="a", name="A")
    second = await make_spot(slug="b", name="B")
    for spot in (first, second):
        await auth_client.post(
            f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
        )

    reordered = await auth_client.put(
        "/api/v1/spots/favorites/order", json={"spot_ids": [second.id]}
    )

    assert [item["id"] for item in reordered.json()] == [second.id, first.id]


async def test_reordering_a_spot_that_is_not_a_favorite_is_refused(
    auth_client, make_spot
) -> None:
    spot = await make_spot()

    response = await auth_client.put(
        "/api/v1/spots/favorites/order", json={"spot_ids": [spot.id]}
    )

    assert response.status_code == 422


# ── Les annonces ───────────────────────────────────────────────────────────


async def test_a_favorite_without_rules_is_never_announced(
    auth_client, make_spot, make_forecast
) -> None:
    """Sans règles, « correspond » ne veut rien dire.

    Tous les créneaux correspondraient, et Jour afficherait trois annonces
    permanentes qu'on cesserait de lire en deux jours.
    """
    spot = await make_spot()
    await auth_client.post(
        f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
    )
    await make_forecast(spot, start=datetime.now(UTC))

    response = await auth_client.get("/api/v1/spots/matches")

    assert response.status_code == 200
    assert response.json() == []


async def test_a_matching_favorite_is_announced_in_the_conditional(
    auth_client, make_spot, make_forecast
) -> None:
    """« Parlementia devrait marcher — demain 10 h à 13 h ».

    Le conditionnel est voulu : des critères larges confrontés à une prévision
    ne sont pas une promesse.
    """
    spot = await make_spot(slug="parlementia", name="Parlementia")
    await auth_client.post(
        f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
    )
    # La fixture pose houle 1,4 m / 12 s / 285° et vent 8 kt d'est : elle
    # correspond exactement à ces critères-là.
    await auth_client.put(
        f"/api/v1/spots/{spot.id}/rules", json=PARLEMENTIA_RULES
    )
    await make_forecast(
        spot, start=datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    )

    response = await auth_client.get("/api/v1/spots/matches")
    body = response.json()

    assert body, "aucune fenêtre annoncée"
    assert body[0]["spot"]["name"] == "Parlementia"
    assert body[0]["sentence"].startswith("Parlementia devrait marcher")
    assert "m /" in body[0]["details"]
    # Les plus proches d'abord : ce qui se décide ce soir passe devant dimanche.
    starts = [datetime.fromisoformat(item["start"]) for item in body]
    assert starts == sorted(starts)


async def test_a_spot_outside_its_rules_is_not_announced(
    auth_client, make_spot, make_forecast
) -> None:
    """La houle vient du sud, ses secteurs disent ouest."""
    spot = await make_spot()
    await auth_client.post(
        f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
    )
    await auth_client.put(
        f"/api/v1/spots/{spot.id}/rules", json=PARLEMENTIA_RULES
    )
    await make_forecast(
        spot,
        start=datetime.now(UTC).replace(minute=0, second=0, microsecond=0),
        wave_direction_deg=180.0,
    )

    assert (await auth_client.get("/api/v1/spots/matches")).json() == []


async def test_the_main_favorite_is_not_announced_twice(
    auth_client, make_spot, make_forecast, user, db_session
) -> None:
    """Sa prévision est déjà en grand sur Jour : l'annoncer ferait doublon.

    L'écran le dit autrement, par `home_matches` dans le bloc de mer.
    """
    spot = await make_spot()
    await auth_client.post(
        f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
    )
    await auth_client.put(
        f"/api/v1/spots/{spot.id}/rules", json=PARLEMENTIA_RULES
    )
    await auth_client.put("/api/v1/auth/me/profile", json={"home_spot_id": spot.id})
    await make_forecast(
        spot, start=datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    )

    assert (await auth_client.get("/api/v1/spots/matches")).json() == []
    # Il reste visible quand on le demande explicitement.
    included = await auth_client.get("/api/v1/spots/matches?include_home=true")
    assert included.json()


async def test_the_day_screen_gets_its_announcements_in_one_call(
    auth_client, make_spot, make_forecast, monkeypatch
) -> None:
    """Jour ne fait qu'un aller-retour : les annonces voyagent avec la reco."""
    from app.services import recommend as recommend_service

    async def _no_refresh(db, spots, timeout_s=None):
        return []

    monkeypatch.setattr(recommend_service, "ensure_fresh", _no_refresh)

    home = await make_spot(slug="home", name="Maison")
    other = await make_spot(slug="autre", name="Lafitenia", lat=43.39, lon=-1.67)
    for spot in (home, other):
        await auth_client.post(
            f"/api/v1/spots/{spot.id}/favorite", json={"favorite": True}
        )
        await make_forecast(
            spot,
            start=datetime.now(UTC).replace(minute=0, second=0, microsecond=0),
        )
    await auth_client.put(f"/api/v1/spots/{other.id}/rules", json=PARLEMENTIA_RULES)
    await auth_client.put("/api/v1/auth/me/profile", json={"home_spot_id": home.id})

    response = await auth_client.get("/api/v1/recommend?lat=43.66&lon=-1.44")
    body = response.json()

    # Seul Lafitenia a des critères — le favori principal est écarté, et la
    # journée en donne une fenêtre par jour de jour, trois au maximum.
    assert {item["spot"]["name"] for item in body["matches"]} == {"Lafitenia"}
    assert 1 <= len(body["matches"]) <= 3
    # Le favori principal n'a pas de critères : il ne « correspond » à rien.
    assert body["home_matches"] is False
