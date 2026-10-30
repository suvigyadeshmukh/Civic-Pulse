"""Civic Pulse — SQLAlchemy 2.0 async database engine, session factory, and
declarative ``Base`` with a standardised naming convention.

Provides:
    * ``engine`` — shared async engine (``asyncpg``)
    * ``AsyncSessionLocal`` — session factory producing ``AsyncSession`` instances
    * ``Base`` — declarative base for all ORM models
    * ``get_async_session()`` — async-generator yielding a managed session
    * ``verify_db_connection_and_extensions()`` — startup probe
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Naming conventions — guarantees deterministic constraint names so Alembic
# autogenerate diffs are reproducible across developer machines.
# ---------------------------------------------------------------------------
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Shared declarative base inherited by every Civic Pulse ORM model.

    The ``metadata`` object carries a naming convention so that all constraints
    and indexes receive deterministic names, avoiding Alembic autogenerate
    noise across environments.
    """

    metadata = metadata


# ---------------------------------------------------------------------------
# Engine & session factory — instantiated once at module import time so the
# pool is shared across the entire process.
# ---------------------------------------------------------------------------
_settings = get_settings()

engine = create_async_engine(
    _settings.DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=_settings.DEBUG and _settings.LOG_LEVEL == "debug",
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-compatible dependency that yields a scoped ``AsyncSession``.

    The session is committed on success and rolled back + closed on error.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Startup verification — called once inside the FastAPI lifespan manager.
# ---------------------------------------------------------------------------
_REQUIRED_EXTENSIONS = {"vector", "postgis", "pgcrypto"}


async def verify_db_connection_and_extensions() -> dict[str, object]:
    """Connect to PostgreSQL and verify that required extensions are loaded.

    Returns a dict summarising the verification result, e.g.::

        {
            "connected": True,
            "extensions_found": ["pgcrypto", "postgis", "uuid-ossp", "vector"],
            "missing": [],
        }

    Raises
    ------
    RuntimeError
        If the database is unreachable or a required extension is missing.
    """
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT extname FROM pg_extension"))
        installed: set[str] = {row[0] for row in rows}

    missing = _REQUIRED_EXTENSIONS - installed

    result: dict[str, object] = {
        "connected": True,
        "extensions_found": sorted(installed),
        "missing": sorted(missing),
    }

    if missing:
        msg = (
            f"Required PostgreSQL extensions missing: {sorted(missing)}. "
            "Ensure init-extensions.sql ran during container init."
        )
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("Database OK — extensions verified: %s", sorted(installed))
    return result

