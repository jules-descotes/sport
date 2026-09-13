"""Un 500 doit se lire comme un 500, pas comme une erreur CORS.

Le 13/09, `PATCH /sessions/1` avec des segments répondait 500 et le navigateur
affichait « blocked by CORS policy ». On a donc cherché une origine mal
déclarée pendant que la base refusait une ligne. Ces tests existent pour que
ça n'arrive plus : la réponse d'erreur porte les en-têtes CORS, donc le vrai
statut est visible côté navigateur.
"""
from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

ORIGIN = "http://localhost:3000"


@pytest.fixture
def boom_route():
    """Une route qui lève, montée le temps du test puis retirée.

    Montée à la main plutôt qu'en dur dans `main.py` : une route qui plante
    exprès n'a rien à faire dans le schéma OpenAPI de production.
    """

    @app.get("/api/v1/_boom")
    async def _boom() -> dict[str, str]:  # pragma: no cover - lève toujours
        raise RuntimeError("segment en double")

    yield "/api/v1/_boom"

    app.router.routes = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) != "/api/v1/_boom"
    ]
    app.openapi_schema = None


async def test_an_unhandled_error_answers_json_with_cors(boom_route) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(boom_route, headers={"Origin": ORIGIN})

    assert response.status_code == 500
    # C'est cette ligne qui manquait en production.
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["content-type"].startswith("application/json")


async def test_the_error_body_is_sober_and_carries_an_id(boom_route) -> None:
    """Un identifiant pour retrouver la ligne de log, et rien d'autre."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(boom_route, headers={"Origin": ORIGIN})

    body = response.json()
    assert body["detail"] == "Erreur interne"
    assert body["error_id"]
    assert len(body["error_id"]) == 12
    # Surtout pas de traceback dans la réponse.
    assert "Traceback" not in response.text
    assert "segment en double" not in response.text


async def test_two_errors_get_two_identifiers(boom_route) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = (await client.get(boom_route)).json()["error_id"]
        second = (await client.get(boom_route)).json()["error_id"]

    assert first != second


async def test_the_traceback_still_reaches_the_logs(boom_route, caplog) -> None:
    """Sobre pour le navigateur, complet pour Railway."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    with caplog.at_level("ERROR"):
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.get(boom_route)

    assert any("segment en double" in record.getMessage() or
               (record.exc_info and "segment en double" in str(record.exc_info[1]))
               for record in caplog.records)


async def test_a_normal_error_is_untouched(client) -> None:
    """404 et 401 passent par `ExceptionMiddleware`, en dessous : rien ne change."""
    response = await client.get("/api/v1/sessions/999999")

    assert response.status_code == 401
    assert "error_id" not in response.text
