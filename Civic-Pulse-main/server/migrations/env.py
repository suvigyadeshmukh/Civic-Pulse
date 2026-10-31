"""Alembic environment for the Civic Pulse PostgreSQL schema.

The migration URL is read from ``get_settings().SYNC_DATABASE_URL`` so Alembic
always targets the same database as the application (including a root ``.env``).
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import every domain model module so ``Base.metadata`` is fully populated for
# autogenerate and revision execution.
import app.domains.grievance_triage.models  # noqa: F401
import app.domains.identity.models  # noqa: F401
import app.domains.policy_explainer.models  # noqa: F401
from app.core.database import Base
from app.core.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

target_metadata = Base.metadata

# PostGIS installs its own reference/TIGER/topology tables. They are extension
# internals, not application schema, so keep them out of autogenerate/check.
_POSTGIS_SYSTEM_SCHEMAS = {"tiger", "topology"}
_POSTGIS_SYSTEM_TABLES = {"spatial_ref_sys"}


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Exclude PostGIS extension internals from Alembic comparisons."""
    if type_ == "table":
        if name in _POSTGIS_SYSTEM_TABLES:
            return False
        if getattr(object_, "schema", None) in _POSTGIS_SYSTEM_SCHEMAS:
            return False
    return True


def _database_url() -> str:
    """Return the synchronous SQLAlchemy URL used by Alembic."""
    return get_settings().SYNC_DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live PostgreSQL database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # PostGIS images put ``topology`` and ``tiger`` on the search_path. Pin
        # autogenerate/check to ``public`` so extension internals are not
        # reflected as application tables with ``schema=None``.
        connection.exec_driver_sql("SET search_path TO public")

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
