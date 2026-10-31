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
    # Bound connection attempts so startup and /health degrade quickly when
    # PostgreSQL is unreachable (the Docker Desktop proxy can accept a TCP
    # connection for a stopped container and leave the handshake hanging).
    connect_args={"timeout": 3},
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
_REQUIRED_EXTENSIONS: list[str] = ["pgcrypto", "postgis", "uuid-ossp", "vector"]


def _classify_extension_error(exc: Exception) -> str:
    """Return a short, credential-safe reason for a failed extension creation."""
    orig = getattr(exc, "orig", None) or exc
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    message = str(exc).lower()

    if sqlstate == "42501" or "permission denied" in message or "insufficient privilege" in message:
        return "insufficient database privileges"
    if sqlstate == "58P01" or "could not open extension control file" in message:
        return "extension not available on the server"
    return type(exc).__name__


async def verify_db_connection_and_extensions() -> dict[str, object]:
    """Connect to PostgreSQL, create missing extensions, and report availability.

    Extension creation failures are logged but never abort startup: a missing
    extension or an account without ``CREATE EXTENSION`` privileges leaves the
    database in a degraded-but-usable state. Connection failures are likewise
    reported as degraded instead of raising.

    Returns
    -------
    dict[str, object]
        ``{"database": "connected", "extensions": [...]}`` on success, or
        ``{"database": "degraded (<ExceptionType>)", "extensions": []}`` when
        PostgreSQL is unavailable. Credentials and connection strings are
        never included in the result.
    """
    try:
        async with engine.begin() as conn:
            creation_failures: dict[str, str] = {}

            for ext in _REQUIRED_EXTENSIONS:
                # A savepoint keeps a failed CREATE EXTENSION from aborting the
                # outer transaction, so the remaining extensions can still be
                # attempted and the final catalog query can still run.
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            text(f'CREATE EXTENSION IF NOT EXISTS "{ext}";')
                        )
                except Exception as exc:
                    reason = _classify_extension_error(exc)
                    creation_failures[ext] = reason
                    logger.warning(
                        "Could not create PostgreSQL extension '%s': %s.",
                        ext,
                        reason,
                    )

            res = await conn.execute(
                text(
                    """
                    SELECT extname
                    FROM pg_extension
                    WHERE extname IN (
                        'uuid-ossp',
                        'pgcrypto',
                        'vector',
                        'postgis'
                    )
                    ORDER BY extname;
                    """
                )
            )
            installed = [row[0] for row in res.fetchall()]

        missing = [ext for ext in _REQUIRED_EXTENSIONS if ext not in installed]
        for ext in missing:
            reason = creation_failures.get(ext)
            if reason:
                logger.warning(
                    "PostgreSQL extension '%s' is not installed (%s).",
                    ext,
                    reason,
                )
            else:
                logger.warning(
                    "PostgreSQL extension '%s' is not installed.",
                    ext,
                )

        if not missing:
            logger.info(
                "Database connected — required extensions verified: %s",
                installed,
            )

        return {
            "database": "connected",
            "extensions": installed,
        }

    except Exception as exc:
        # Report only the exception class: messages from asyncpg may contain
        # usernames, hosts, or other connection details.
        logger.warning(
            "Database connection verification failed (%s); "
            "continuing in degraded mode.",
            type(exc).__name__,
        )
        return {
            "database": f"degraded ({type(exc).__name__})",
            "extensions": [],
        }

