from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.routes.auth import router as auth_router
from app.api.routes.daily_log import router as daily_log_router
from app.api.routes.expenditure import router as expenditure_router
from app.api.routes.gear import router as gear_router
from app.api.routes.generator import router as generator_router
from app.api.routes.habits import router as habits_router
from app.api.routes.nutrition import router as nutrition_router
from app.api.routes.recommend import router as recommend_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.spots import router as spots_router
from app.api.routes.tides import router as tides_router
from app.api.routes.training import router as training_router
from app.core.config import settings
from app.core.errors import ServerErrorJsonMiddleware
from app.core.security import hash_password
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.database import async_session

# Import des modèles : enregistre les métadonnées SQLAlchemy (et fournit à
# Alembic la cible de l'autogénération).
from app.models.api_quota import ApiQuota  # noqa: F401
from app.models.api_token import ApiToken  # noqa: F401
from app.models.daily_log import DailyLog  # noqa: F401
from app.models.exercise import Exercise  # noqa: F401
from app.models.forecast import Forecast, Observation  # noqa: F401
from app.models.formula import Formula, FormulaItem  # noqa: F401
from app.models.gear import Gear  # noqa: F401
from app.models.habit import Habit, HabitEvent  # noqa: F401
from app.models.nutrition import (  # noqa: F401
    BodyMetric,
    Food,
    FoodLog,
    MealPlan,
    MealPlanItem,
    NutritionProfile,
    Recipe,
    RecipeItem,
)
from app.models.objective import (  # noqa: F401
    Objective,
    ObjectiveMeasurement,
)
from app.models.profile import Profile  # noqa: F401
from app.models.session_segment import SessionSegment  # noqa: F401
from app.models.spot import Spot, SpotPreference  # noqa: F401
from app.models.spot_rule import SpotRule  # noqa: F401
from app.models.surf_session import SurfSession  # noqa: F401
from app.models.thresholds import UserThresholds  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.workout import WorkoutSession, WorkoutSet  # noqa: F401

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


def log_candhis_state() -> None:
    """Dit au démarrage si les bouées sont branchées, et sur quoi.

    Une fonctionnalité éteinte doit le dire à l'allumage, pas se manifester
    trois semaines plus tard par un écran vide que personne ne sait expliquer.
    Le fuseau est journalisé avec, parce qu'il n'est **pas** documenté par le
    Cerema (cf. docs/CANDHIS.md §5) : le jour où une mesure tombe à côté de la
    prévision, la première ligne à relire est celle-ci.
    """
    if settings.candhis_enabled:
        logger.info(
            "CANDHIS actif : %s, plafond %d appels/jour, horodatages lus en %s",
            settings.candhis_url,
            settings.candhis_daily_call_cap,
            settings.candhis_tz,
        )
    else:
        logger.info(
            "CANDHIS inactif : CANDHIS_API_KEY absente. Les bouées ne sont pas "
            "interrogées, le reste fonctionne normalement."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import start_scheduler, stop_scheduler

    # Le schéma est la propriété d'Alembic : `run.py` applique les migrations
    # avant de lancer uvicorn. Rien n'est créé ici.
    await create_default_user()
    log_candhis_state()
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

# Déclaré **avant** CORS, donc exécuté après lui : c'est toute l'astuce. Un
# `add_exception_handler(Exception, ...)` finirait dans `ServerErrorMiddleware`,
# au-dessus de CORS, et sa réponse 500 repartirait sans
# `Access-Control-Allow-Origin` — le navigateur afficherait alors une erreur
# CORS à la place du vrai statut (constaté le 13/09 sur `PATCH /sessions/1`).
app.add_middleware(ServerErrorJsonMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ajouté **après** CORS, donc exécuté avant lui : Starlette empile les
# middlewares à l'envers de leur déclaration. C'est ce qu'on veut — les
# en-têtes de sécurité se posent sur toutes les réponses, y compris les
# préflights auxquels CORS répond sans descendre plus bas, et la redirection
# http → https tombe avant tout le reste.
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(spots_router, prefix="/api/v1")
app.include_router(tides_router, prefix="/api/v1")
app.include_router(recommend_router, prefix="/api/v1")
app.include_router(daily_log_router, prefix="/api/v1")
app.include_router(expenditure_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(gear_router, prefix="/api/v1")
app.include_router(training_router, prefix="/api/v1")
# Après `training_router` : ses routes fixes (`/training/overview`…) sont
# déjà déclarées, et celles-ci le sont aussi — aucune n'est paramétrée.
app.include_router(generator_router, prefix="/api/v1")
app.include_router(nutrition_router, prefix="/api/v1")
app.include_router(habits_router, prefix="/api/v1")


if settings.storage_backend == "local":
    # Développement seulement : en production les photos vivent sur R2 et sont
    # servies par son domaine public. Monter un répertoire depuis le conteneur
    # Railway n'aurait aucun sens — son disque est éphémère.
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    media_root = Path(settings.media_dir)
    media_root.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_root), name="media")


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
