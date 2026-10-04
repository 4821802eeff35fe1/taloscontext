"""Test fixtures.

By default tests run hermetically on in-memory SQLite + fakeredis. Set
TEST_DATABASE_URL (postgresql+asyncpg://...) and/or TEST_REDIS_URL to run the
same suite against real services — CI/local verification of anything that
behaves differently on Postgres (enums, RETURNING, FK enforcement).
"""
import os

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("TELETHON_SESSION_ENCRYPTION_KEY", "test-encryption-key-for-pytest")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("USE_FAKE_AI_PROVIDER", "true")
os.environ.setdefault("USE_FAKE_IMAGE_PROVIDER", "true")
os.environ.setdefault("USE_FAKE_TELEGRAM_PROVIDER", "true")

import uuid

import fakeredis
import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.redis import set_redis_client
from app.db.base import Base
from app.models.identity import Workspace

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL")


@pytest_asyncio.fixture
async def engine():
    if TEST_DATABASE_URL:
        eng = create_async_engine(TEST_DATABASE_URL)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    else:
        eng = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,  # one shared in-memory DB across sessions
        )

        @event.listens_for(eng.sync_engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce FKs like Postgres does
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def redis_client():
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True) if TEST_REDIS_URL else fakeredis.FakeAsyncRedis(decode_responses=True)
    await client.flushdb()
    set_redis_client(client)
    yield client
    await client.flushdb()
    set_redis_client(None)
    await client.aclose()


@pytest_asyncio.fixture
async def workspace(db_session) -> Workspace:
    ws = Workspace(name="Test WS", slug=f"test-{uuid.uuid4().hex[:8]}")
    db_session.add(ws)
    await db_session.flush()
    return ws


@pytest_asyncio.fixture
async def client(session_factory, redis_client, monkeypatch):
    """HTTP client against the real ASGI app, wired to the test DB/Redis."""
    from app.api.deps import get_db
    from app.jobs import queue as queue_module
    from app.main import app

    async def _get_db():
        async with session_factory() as session:
            yield session

    class _FakePool:
        def __init__(self):
            self.jobs: list[tuple] = []

        async def enqueue_job(self, name, *args, **kwargs):
            self.jobs.append((name, args, kwargs))
            return object()

        async def ping(self):
            return True

    pool = _FakePool()

    async def _get_pool():
        return pool

    monkeypatch.setattr(queue_module, "get_arq_pool", _get_pool)
    app.dependency_overrides[get_db] = _get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.arq_pool = pool  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def register(client: httpx.AsyncClient, email: str, workspace_name: str = "WS") -> str:
    """Registers a user (cookie stays on the client) and returns their workspace id."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret123", "full_name": "T", "workspace_name": workspace_name},
    )
    assert r.status_code == 201, r.text
    ws = await client.get("/api/v1/workspaces")
    return ws.json()[0]["id"]
