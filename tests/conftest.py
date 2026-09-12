from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.database import Base, get_db
from app.main import app
from app.models.profile import Profile
from app.models.user import User

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

TEST_EMAIL = "jules@example.com"
TEST_PASSWORD = "surf-and-code-2026"


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
