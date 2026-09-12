from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.db.database import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, ProfileUpdate, Token, UserRead
from app.services.auth_service import authenticate_user, get_current_active_user
from app.services.spot_tiers import get_or_create_preferences, recompute_tiers

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_MAX_AGE_SECONDS = 60 * 60 * 24


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS * settings.access_token_expire_days,
        httponly=True,
        secure=not settings.debug,
        # sport et api-sport partagent atelier-okomi.fr : les requêtes du front
        # vers l'API sont same-site, `lax` suffit et protège du CSRF tiers.
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain or None,
    )


@router.post("/login", response_model=Token)
async def login(
    data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> Token:
    user = await authenticate_user(db, data.email, data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé"
        )

    token = create_access_token({"sub": user.email})
    _set_session_cookie(response, token)

    # Les niveaux d'ingestion se recalculent à chaque connexion : le catalogue
    # a pu grossir depuis le dernier import OSM, et un spot nouvellement importé
    # dans le rayon doit devenir « potentiel » sans attendre.
    preferences = await get_or_create_preferences(db, user.id)
    await recompute_tiers(db, preferences)

    return Token(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain or None,
    )


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_active_user)) -> User:
    return current_user


@router.put("/me/profile", response_model=UserRead)
async def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    from app.models.profile import Profile

    profile = current_user.profile
    if profile is None:
        profile = Profile(user_id=current_user.id)
        db.add(profile)
        current_user.profile = profile

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(current_user, attribute_names=["profile"])
    return current_user
