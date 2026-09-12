"""En-têtes de sécurité, redirection http → https, et refus des webcams en clair.

Le site est en production et c'est là qu'il est testé : ces tests sont le seul
moyen de savoir qu'un en-tête est encore posé après un refactor. Un HSTS qui
disparaît ne casse rien de visible — il rouvre juste la porte, en silence.
"""
from __future__ import annotations

import httpx
import pytest

from app.core import security_headers
from app.core.config import settings
from app.services import webcams
from app.services.webcams import WebcamUrlError, normalize_webcam_url

PRODUCTION_HOST = "api-sport.atelier-okomi.fr"


async def test_security_headers_are_present_on_every_response(client) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=(self)" in response.headers["Permissions-Policy"]
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_api_csp_allows_nothing_and_upgrades_the_insecure(client) -> None:
    """Une API ne rend que du JSON : elle n'a besoin d'aucune source."""
    csp = (await client.get("/health")).headers["Content-Security-Policy"]

    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "upgrade-insecure-requests" in csp


async def test_docs_get_their_own_policy(client) -> None:
    """Swagger charge ses scripts depuis jsDelivr : une politique à part, et
    pas une porte ouverte sur toute l'API."""
    csp = (await client.get("/docs")).headers["Content-Security-Policy"]

    assert "https://cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp
    # L'exception ne déborde pas sur le reste.
    health = (await client.get("/health")).headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" not in health


async def test_hsts_is_posed_in_production(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "debug", False)

    response = await client.get("/health", headers={"host": PRODUCTION_HOST})

    assert (
        response.headers["Strict-Transport-Security"]
        == "max-age=31536000; includeSubDomains"
    )
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
    assert "includeSubDomains" in response.headers["Strict-Transport-Security"]


async def test_hsts_stays_off_on_localhost(client, monkeypatch) -> None:
    """Un an de HSTS sur `localhost` condamnerait tous les projets de la
    machine à refuser `http://localhost`."""
    monkeypatch.setattr(settings, "debug", False)

    response = await client.get("/health", headers={"host": "localhost:8000"})

    assert "Strict-Transport-Security" not in response.headers


async def test_plain_http_is_redirected_in_production(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "debug", False)

    response = await client.get(
        "/health",
        headers={"host": PRODUCTION_HOST, "x-forwarded-proto": "http"},
    )

    # 308 et pas 301 : un 301 transformerait le POST du raccourci iPhone en GET.
    assert response.status_code == 308
    assert response.headers["location"].startswith(f"https://{PRODUCTION_HOST}")


async def test_https_requests_are_served_normally(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "debug", False)

    response = await client.get(
        "/health",
        headers={"host": PRODUCTION_HOST, "x-forwarded-proto": "https"},
    )

    assert response.status_code == 200


def test_security_headers_module_declares_a_full_year() -> None:
    assert security_headers.HSTS_VALUE == "max-age=31536000; includeSubDomains"


# ── URL de webcam ──────────────────────────────────────────────────────────


async def test_https_webcam_url_passes_through() -> None:
    url = "https://www.youtube.com/embed/abc"
    assert await normalize_webcam_url(url) == url


async def test_empty_webcam_url_clears_the_field() -> None:
    assert await normalize_webcam_url(None) is None
    assert await normalize_webcam_url("   ") is None


async def test_non_http_schemes_are_refused() -> None:
    with pytest.raises(WebcamUrlError):
        await normalize_webcam_url("javascript:alert(1)")
    with pytest.raises(WebcamUrlError):
        await normalize_webcam_url("ftp://cam.example.com/live")


async def test_plain_http_is_rewritten_when_the_site_serves_https(monkeypatch) -> None:
    async def _serves(url: str, client=None) -> bool:
        assert url == "https://cam.example.com/plage"
        return True

    monkeypatch.setattr(webcams, "_serves_https", _serves)

    assert (
        await normalize_webcam_url("http://cam.example.com/plage")
        == "https://cam.example.com/plage"
    )


async def test_plain_http_is_refused_when_https_is_not_served(monkeypatch) -> None:
    async def _serves(url: str, client=None) -> bool:
        return False

    monkeypatch.setattr(webcams, "_serves_https", _serves)

    with pytest.raises(WebcamUrlError) as excinfo:
        await normalize_webcam_url("http://cam.example.com/plage")

    assert "contenu mixte" in str(excinfo.value)


async def test_patching_a_spot_with_an_http_webcam_returns_422(
    auth_client, make_spot, monkeypatch
) -> None:
    async def _serves(url: str, client=None) -> bool:
        return False

    monkeypatch.setattr(webcams, "_serves_https", _serves)
    spot = await make_spot()

    response = await auth_client.patch(
        f"/api/v1/spots/{spot.slug}",
        json={"webcam_url": "http://cam.example.com/plage"},
    )

    assert response.status_code == 422


async def test_patching_a_spot_upgrades_the_webcam_to_https(
    auth_client, make_spot, monkeypatch
) -> None:
    async def _serves(url: str, client=None) -> bool:
        return True

    monkeypatch.setattr(webcams, "_serves_https", _serves)
    spot = await make_spot()

    response = await auth_client.patch(
        f"/api/v1/spots/{spot.slug}",
        json={"webcam_url": "http://cam.example.com/plage"},
    )

    assert response.status_code == 200
    assert response.json()["webcam_url"] == "https://cam.example.com/plage"


async def test_webcam_can_be_removed(auth_client, make_spot) -> None:
    """Retirer une webcam est un geste normal : il ne doit pas être refusé."""
    spot = await make_spot()
    await auth_client.patch(
        f"/api/v1/spots/{spot.slug}",
        json={"webcam_url": "https://www.youtube.com/embed/abc"},
    )

    response = await auth_client.patch(
        f"/api/v1/spots/{spot.slug}", json={"webcam_url": None}
    )

    assert response.status_code == 200
    assert response.json()["webcam_url"] is None


async def test_probe_never_raises_on_a_dead_host(monkeypatch) -> None:
    """Un site injoignable est un refus, jamais une exception qui remonte."""

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return None

        def stream(self, method, url):
            raise httpx.ConnectError("injoignable")

    monkeypatch.setattr(webcams.httpx, "AsyncClient", lambda **kwargs: FailingClient())

    with pytest.raises(WebcamUrlError):
        await normalize_webcam_url("http://cam.example.com/plage")
