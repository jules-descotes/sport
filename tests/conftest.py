from __future__ import annotations

import math
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.database import Base, get_db
from app.main import app
from app.models.enums import SpotSource, SpotTier
from app.models.forecast import Forecast
from app.models.profile import Profile
from app.models.spot import Spot, SpotPreference
from app.models.user import User

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

TEST_EMAIL = "jules@example.com"
TEST_PASSWORD = "surf-and-code-2026"

# Côte landaise : plage orientée plein ouest. Le trait de côte OSM y court du
# nord vers le sud (terre à gauche), donc cap 180° et normale sortante 270°.
HOSSEGOR_LAT = 43.6640
HOSSEGOR_LON = -1.4400
ONSHORE_WEST = 270.0


@pytest.fixture
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncSession:
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db_session) -> AsyncClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # ASGITransport ne déclenche pas le lifespan : ni l'ordonnanceur ni la
    # création de l'utilisateur par défaut ne tournent pendant les tests.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def user(db_session) -> User:
    user = User(
        email=TEST_EMAIL,
        hashed_password=hash_password(TEST_PASSWORD),
        is_active=True,
    )
    user.profile = Profile(disciplines=["surf"])
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def auth_client(client: AsyncClient, user: User) -> AsyncClient:
    """Client déjà connecté — le cookie de session suffit ensuite."""
    await client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return client


@pytest.fixture
async def preferences(db_session, user: User) -> SpotPreference:
    """Domicile sur la côte landaise, rayon 40 km."""
    preferences = SpotPreference(
        user_id=user.id,
        radius_km=40.0,
        home_lat=HOSSEGOR_LAT,
        home_lon=HOSSEGOR_LON,
        favorite_spot_ids=[],
        hidden_spot_ids=[],
    )
    db_session.add(preferences)
    await db_session.commit()
    await db_session.refresh(preferences)
    return preferences


# ── Fabriques ──────────────────────────────────────────────────────────────


@pytest.fixture
def make_spot(db_session):
    async def _make(
        name: str = "La Gravière",
        lat: float = HOSSEGOR_LAT,
        lon: float = HOSSEGOR_LON,
        slug: Optional[str] = None,
        onshore_dir_deg: Optional[float] = ONSHORE_WEST,
        tier: str = SpotTier.POTENTIAL.value,
        source: str = SpotSource.OSM.value,
        osm_type: Optional[str] = "node",
        osm_id: Optional[int] = None,
    ) -> Spot:
        spot = Spot(
            slug=slug or name.lower().replace(" ", "-").replace("è", "e"),
            name=name,
            lat=lat,
            lon=lon,
            onshore_dir_deg=onshore_dir_deg,
            coast_bearing_deg=(
                None if onshore_dir_deg is None else (onshore_dir_deg - 90) % 360
            ),
            tier=tier,
            is_active=tier != SpotTier.CATALOG.value,
            source=source,
            osm_type=osm_type if source == SpotSource.OSM.value else None,
            osm_id=osm_id if source == SpotSource.OSM.value else None,
        )
        db_session.add(spot)
        await db_session.commit()
        await db_session.refresh(spot)
        return spot

    return _make


@pytest.fixture
def make_forecast(db_session):
    """Écrit des heures de prévision, par défaut propres et surfables."""

    async def _make(
        spot: Spot,
        start: Optional[datetime] = None,
        hours: int = 48,
        fetched_at: Optional[datetime] = None,
        wave_height_m: float = 1.4,
        wave_period_s: float = 12.0,
        wave_direction_deg: float = 285.0,
        wind_speed_kt: float = 8.0,
        wind_direction_deg: float = 90.0,
    ) -> list[Forecast]:
        start = start or datetime.now(UTC).replace(
            minute=0, second=0, microsecond=0
        )
        fetched_at = fetched_at or datetime.now(UTC)

        rows: list[Forecast] = []
        for hour in range(hours):
            ts = start + timedelta(hours=hour)
            # Niveau de la mer sinusoïdal, période 12 h 25 : de quoi donner une
            # position dans la marée et un sens crédibles.
            sea_level = 1.8 * math.sin(2 * math.pi * hour / 12.42)
            forecast = Forecast(
                spot_id=spot.id,
                ts=ts,
                source="open-meteo",
                model="meteofrance_wave",
                model_version="mfwam-2025",
                wave_height_m=wave_height_m,
                wave_period_s=wave_period_s,
                wave_peak_period_s=wave_period_s,
                wave_direction_deg=wave_direction_deg,
                wind_speed_kt=wind_speed_kt,
                wind_gust_kt=wind_speed_kt * 1.4,
                wind_direction_deg=wind_direction_deg,
                sea_level_m=round(sea_level, 3),
                water_temperature_c=18.0,
                fetched_at=fetched_at,
            )
            db_session.add(forecast)
            rows.append(forecast)

        await db_session.commit()
        return rows

    return _make


@pytest.fixture
def patch_session_factory(monkeypatch):
    """Fait pointer le `async_session` d'un module vers la session de test.

    Les jobs planifiés et les rafraîchissements détachés ouvrent leur propre
    session : sans ça, ils taperaient la vraie base de développement.
    """

    def _patch(module, session: AsyncSession) -> None:
        @asynccontextmanager
        async def _scope():
            yield session

        monkeypatch.setattr(module, "async_session", lambda: _scope())

    return _patch
