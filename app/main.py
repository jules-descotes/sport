from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.routes.auth import router as auth_router
from app.core.config import settings
from app.core.security import hash_password
from app.db.database import async_session

# Import des modèles : enregistre les métadonnées SQLAlchemy (et fournit à
# Alembic la cible de l'autogénération).
from app.models.profile import Profile  # noqa: F401
from app.models.user import User  # noqa: F401

# Les journaux applicatifs doivent remonter dans les logs Railway.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.2,
        environment="development" if settings.debug else "production",
        send_default_pii=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
    )


async def create_default_user() -> None:
    """Un seul utilisateur, créé au démarrage depuis ADMIN_EMAIL / ADMIN_PASSWORD.

    Pas de flux d'inscription public : le compte existe ou il est créé ici.
    """
    async with async_session() as session:
        try:
            result = await session.execute(
                select(User).where(User.email == settings.admin_email)
            )
            if result.scalar_one_or_none() is not None:
                logger.info("Utilisateur existant : %s", settings.admin_email)
                return

            user = User(
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                is_active=True,
            )
            user.profile = Profile(disciplines=["surf"])
            session.add(user)
            await session.commit()
            logger.info("Utilisateur créé : %s", settings.admin_email)
        except Exception as exc:
            logger.error("Création de l'utilisateur impossible : %s", exc, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import start_scheduler, stop_scheduler

    # Le schéma est la propriété d'Alembic : `run.py` applique les migrations
    # avant de lancer uvicorn. Rien n'est créé ici.
    await create_default_user()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Sonde Railway (`healthcheckPath`) et état de chargement du front."""
    return {"status": "ok"}
