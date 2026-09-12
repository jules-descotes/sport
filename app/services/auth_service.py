from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_API,
    decode_token,
    verify_password,
)
from app.db.database import get_db
from app.models.api_token import ApiToken
from app.models.user import User


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(
        select(User).options(selectinload(User.profile)).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> Optional[User]:
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def _extract_token(request: Request) -> Optional[str]:
    """Le cookie httpOnly est la voie normale (navigateur, PWA installée).

    L'en-tête Bearer est l'autre voie, et elle n'est pas un pis-aller : le
    raccourci iOS « Obtenir le contenu de l'URL » n'a pas de magasin de
    cookies, et le cookie `Secure` + `SameSite=Lax` de la session ne lui
    parviendrait de toute façon pas. C'est aussi par là que passent /docs et
    les tests.
    """
    cookie_token = request.cookies.get(settings.session_cookie_name)
    if cookie_token:
        return cookie_token
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


async def _api_token_row(db: AsyncSession, jti: str) -> Optional[ApiToken]:
    result = await db.execute(select(ApiToken).where(ApiToken.jti == jti))
    return result.scalar_one_or_none()


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Non authentifié",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _extract_token(request)
    if token is None:
        raise unauthorized

    payload = decode_token(token)
    if payload is None:
        raise unauthorized

    token_type = payload.get("type")
    if token_type not in (TOKEN_TYPE_ACCESS, TOKEN_TYPE_API):
        raise unauthorized

    email = payload.get("sub")
    if not email:
        raise unauthorized

    api_token: Optional[ApiToken] = None
    if token_type == TOKEN_TYPE_API:
        # La signature et l'expiration ne suffisent pas : un JWT valide reste
        # valide après la perte du téléphone. La révocation se lit ici, et
        # nulle part ailleurs.
        jti = payload.get("jti")
        if not jti:
            raise unauthorized
        api_token = await _api_token_row(db, jti)
        if api_token is None or not api_token.is_usable():
            raise unauthorized

    user = await get_user_by_email(db, email)
    if user is None:
        raise unauthorized

    if api_token is not None and api_token.user_id != user.id:
        raise unauthorized

    if api_token is not None:
        # Sert à repérer, dans le profil, le jeton qui ne tourne plus — et donc
        # à le révoquer sans se demander s'il sert encore à quelque chose.
        api_token.last_used_at = datetime.now(UTC)
        await db.commit()

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé"
        )
    return current_user
