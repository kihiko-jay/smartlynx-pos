"""
Alembic environment configuration — Smartlynx 4.5.1

Pulls DATABASE_URL from app.core.config.settings so credentials never live
in alembic.ini. Supports both online (live DB) and offline (SQL script) modes.
"""

import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Ensure the backend app is importable from the alembic/ subdirectory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from app.database import Base

# Import all models so Base.metadata is fully populated
import app.models  # noqa: F401

# Alembic Config object — gives access to values in alembic.ini
config = context.config

# Wire up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object Alembic uses to detect schema drift
target_metadata = Base.metadata

_ALEMBIC_DIR = os.path.dirname(__file__)
_PROFILE_VERSION_LOCATIONS = {
    "legacy": [
        os.path.join(_ALEMBIC_DIR, "versions_legacy"),
    ],
    "bootstrap": [
        os.path.join(_ALEMBIC_DIR, "versions_bootstrap"),
    ],
}


def _resolve_profile() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    profile = (x_args.get("profile") or "legacy").strip().lower()
    if profile not in _PROFILE_VERSION_LOCATIONS:
        valid = ", ".join(sorted(_PROFILE_VERSION_LOCATIONS))
        raise RuntimeError(
            f"Unsupported Alembic profile '{profile}'. Use one of: {valid}."
        )
    return profile


def _configure_version_locations() -> str:
    profile = _resolve_profile()
    # Keep profile-specific execution paths at runtime. alembic.ini still
    # carries a superset version_locations for early revision discovery.
    version_locations = os.pathsep.join(_PROFILE_VERSION_LOCATIONS[profile])
    config.set_main_option("version_locations", version_locations)
    return profile


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL script without
    connecting to the database. Useful for reviewing changes before applying.

    Usage:
        alembic upgrade head --sql > migration.sql
    """
    profile = _configure_version_locations()
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        tag=profile,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — connects to the live database and
    applies changes directly.

    Usage:
        alembic upgrade head
    """
    profile = _configure_version_locations()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,   # NullPool is correct for migration scripts
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            tag=profile,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
