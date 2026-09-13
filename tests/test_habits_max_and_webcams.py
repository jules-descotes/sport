"""Habitudes à réduire, et hôtes de webcam — décidés le 13/09 (retours n° 4).

Les deux tiennent à la même idée : **dire, sans juger et sans bloquer**.

- Un objectif d'habitude peut être un plafond. L'écran ne change pas entre les
  deux sens — un compteur, un objectif, une tendance. Pas de rouge, pas de
  message, pas de série perdue.
- Une URL de webcam qui répond 404 ou qui refuse l'encadrement est
  **enregistrée quand même**, avec un avertissement. Le site peut répondre
  autrement au téléphone de Jules qu'à une requête partie de Railway.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import webcams
from app.services.webcams import check_embeddable


# ── Les habitudes à réduire ────────────────────────────────────────────────


async def test_a_habit_can_have_a_ceiling(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/habits",
        json={
            "name": "Verres",
            "icon": "check",
            "kind": "count",
            "unit": "verres",
            "target": 3,
            "target_period": "week",
            "target_direction": "max",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["target_direction"] == "max"
    assert body["target"] == 3


async def test_the_default_is_still_a_floor(auth_client) -> None:
    """Toutes les habitudes existantes sont des minima, et le restent."""
    response = await auth_client.post(
        "/api/v1/habits", json={"name": "Mobilité", "target": 5}
    )

    assert response.json()["target_direction"] == "min"


async def test_an_unknown_direction_is_refused(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/habits",
        json={"name": "Truc", "target": 2, "target_direction": "vers-le-bas"},
    )

    assert response.status_code == 422


async def test_the_direction_can_be_changed_later(auth_client) -> None:
    created = (
        await auth_client.post(
            "/api/v1/habits", json={"name": "Café", "target": 2}
        )
    ).json()

    updated = await auth_client.patch(
        f"/api/v1/habits/{created['id']}",
        json={"name": "Café", "target": 2, "target_direction": "max"},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["target_direction"] == "max"


async def test_the_counters_do_not_change_with_the_direction(
    auth_client,
) -> None:
    """**Le même écran dans les deux sens.**

    Le compteur compte, quelle que soit l'intention. Un plafond ne se compte
    pas à l'envers, et surtout il ne se compte pas en rouge.
    """
    ceiling = (
        await auth_client.post(
            "/api/v1/habits",
            json={"name": "Verres", "target": 2, "target_direction": "max"},
        )
    ).json()

    await auth_client.post(f"/api/v1/habits/{ceiling['id']}/events", json={})
    await auth_client.post(f"/api/v1/habits/{ceiling['id']}/events", json={})
    await auth_client.post(f"/api/v1/habits/{ceiling['id']}/events", json={})

    rows = (await auth_client.get("/api/v1/habits")).json()
    row = next(item for item in rows if item["id"] == ceiling["id"])

    assert row["today"] == 3
    # Rien dans la réponse ne dit que c'est trop. C'est à l'écran de compter,
    # pas de juger.
    assert set(row) == set(ceiling)


async def test_the_trend_carries_both_averages(auth_client) -> None:
    """Dans les stats de profil, **la tendance suffit**.

    Une moyenne à 7 jours plus basse que celle à 30 se lit toute seule, dans
    les deux sens, sans qu'on ait à dire si c'est bien.
    """
    created = (
        await auth_client.post(
            "/api/v1/habits",
            json={"name": "Verres", "target": 2, "target_direction": "max"},
        )
    ).json()
    await auth_client.post(f"/api/v1/habits/{created['id']}/events", json={})

    stats = (await auth_client.get("/api/v1/habits/stats")).json()
    trend = next(
        item for item in stats["habits"] if item["habit_id"] == created["id"]
    )

    assert trend["average_7d"] > 0
    assert trend["average_30d"] > 0
    assert trend["target_direction"] == "max"
    # Toujours pas de verdict : on rend des nombres et une courbe.
    assert "success" not in trend
    assert "streak" not in trend


# ── Les webcams ────────────────────────────────────────────────────────────


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_an_embeddable_url_raises_no_warning() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"})

    async with _client(handler) as client:
        assert await check_embeddable("https://loujo.fr/cam", client) is None


async def test_a_missing_page_is_reported() -> None:
    """Un 404 donne un cadre blanc, et un cadre blanc ment sur l'image."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(handler) as client:
        warning = await check_embeddable("https://loujo.fr/absent", client)

    assert warning is not None
    assert "404" in warning


@pytest.mark.parametrize("value", ["DENY", "SAMEORIGIN", "deny"])
async def test_x_frame_options_is_reported(value: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"x-frame-options": value})

    async with _client(handler) as client:
        warning = await check_embeddable("https://exemple.test/cam", client)

    assert warning is not None
    assert "X-Frame-Options" in warning


async def test_frame_ancestors_none_is_reported() -> None:
    """La version moderne de `X-Frame-Options`, et la plus courante désormais."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-security-policy": "frame-ancestors 'none'"},
        )

    async with _client(handler) as client:
        warning = await check_embeddable("https://exemple.test/cam", client)

    assert warning is not None
    assert "frame-ancestors" in warning


async def test_frame_ancestors_open_is_fine() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-security-policy": "frame-ancestors https://*"}
        )

    async with _client(handler) as client:
        assert await check_embeddable("https://exemple.test/cam", client) is None


async def test_an_unreachable_url_is_reported_not_refused() -> None:
    """**Un avertissement, jamais un refus.**

    Le site peut répondre autrement au téléphone de Jules qu'à une requête
    partie d'un conteneur Railway — géoblocage, filtrage d'agent, cache.
    Refuser une URL correcte coûterait plus cher que l'accepter en le disant.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("injoignable")

    async with _client(handler) as client:
        warning = await check_embeddable("https://exemple.test/cam", client)

    assert warning is not None
    assert "injoignable" in warning


async def test_the_url_is_saved_even_with_a_warning(
    auth_client, make_spot, monkeypatch
) -> None:
    """La fiche dit ce qu'on a vu ; elle ne jette pas l'adresse."""
    spot = await make_spot()

    async def refuses(url, client=None):
        return "le site renvoie X-Frame-Options: deny"

    monkeypatch.setattr(
        "app.api.routes.spots.check_embeddable", refuses
    )

    response = await auth_client.patch(
        f"/api/v1/spots/{spot.slug}",
        json={"webcam_url": "https://loujo.fr/cam"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["webcam_url"] == "https://loujo.fr/cam"
    assert body["webcam_warning"] is not None


async def test_no_warning_when_all_is_well(
    auth_client, make_spot, monkeypatch
) -> None:
    spot = await make_spot()

    async def fine(url, client=None):
        return None

    monkeypatch.setattr("app.api.routes.spots.check_embeddable", fine)

    body = (
        await auth_client.patch(
            f"/api/v1/spots/{spot.slug}",
            json={"webcam_url": "https://loujo.fr/cam"},
        )
    ).json()

    assert body["webcam_warning"] is None


async def test_removing_the_webcam_probes_nothing(
    auth_client, make_spot, monkeypatch
) -> None:
    """Retirer une webcam doit rester possible sans réseau."""
    spot = await make_spot()
    called = False

    async def spy(url, client=None):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr("app.api.routes.spots.check_embeddable", spy)

    body = (
        await auth_client.patch(
            f"/api/v1/spots/{spot.slug}", json={"webcam_url": None}
        )
    ).json()

    assert body["webcam_url"] is None
    assert called is False
