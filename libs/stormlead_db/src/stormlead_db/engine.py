"""async sqlalchemy engine + session factory."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_ENGINES: dict[tuple[str, int | None], AsyncEngine] = {}
_SESSION_FACTORIES: dict[tuple[int, int], async_sessionmaker[AsyncSession]] = {}


def get_engine(url: str | None = None) -> AsyncEngine:
    dsn = url or os.environ["DATABASE_URL"]
    # we always store the sync dsn in env (psycopg+postgresql://...).
    # convert to asyncpg for the async engine.
    if dsn.startswith("postgresql+psycopg://"):
        dsn = dsn.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    elif dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)

    try:
        loop_key = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_key = None

    key = (dsn, loop_key)
    if key not in _ENGINES:
        _ENGINES[key] = create_async_engine(
            dsn,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
            future=True,
        )
    return _ENGINES[key]


def _session_factory() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    key = (id(engine), id(asyncio.get_running_loop()))
    if key not in _SESSION_FACTORIES:
        _SESSION_FACTORIES[key] = async_sessionmaker(engine, expire_on_commit=False)
    return _SESSION_FACTORIES[key]


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    factory = _session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
