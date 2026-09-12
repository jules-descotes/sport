from __future__ import annotations

from httpx import AsyncClient

from app.core.config import settings
from app.models.user import User
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def test_login_ok_returns_token_and_sets_httponly_cookie(
    client: AsyncClient, user: User
) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]

    cookie = response.cookies.get(settings.session_cookie_name)
    assert cookie, "la session doit être posée en cookie"
    set_cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header


async def test_login_ko_wrong_password(client: AsyncClient, user: User) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": "mauvais-mdp"}
    )

    assert response.status_code == 401
    assert settings.session_cookie_name not in response.cookies


async def test_login_ko_unknown_email(client: AsyncClient, user: User) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "personne@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_rejects_invalid_token(client: AsyncClient, user: User) -> None:
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer pas-un-jwt"}
    )

    assert response.status_code == 401


async def test_me_with_session_cookie(client: AsyncClient, user: User) -> None:
    """Parcours réel du front : le cookie posé au login suffit, le front ne
    manipule jamais le jeton."""
    await client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == TEST_EMAIL
    assert body["profile"]["disciplines"] == ["surf"]


async def test_me_with_bearer_token(client: AsyncClient, user: User) -> None:
    """Voie de secours pour /docs et le raccourci iPhone du lot 2."""
    login = await client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    token = login.json()["access_token"]
    client.cookies.clear()

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == TEST_EMAIL


async def test_logout_clears_session(client: AsyncClient, user: User) -> None:
    await client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )

    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
