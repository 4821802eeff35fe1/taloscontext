import os

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("TELETHON_SESSION_ENCRYPTION_KEY", "test-encryption-key-for-pytest")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("USE_FAKE_AI_PROVIDER", "true")
os.environ.setdefault("USE_FAKE_IMAGE_PROVIDER", "true")
os.environ.setdefault("USE_FAKE_TELEGRAM_PROVIDER", "true")

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.db.base import Base


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()
