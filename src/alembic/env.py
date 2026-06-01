"""Alembic environment configuration.

Configures Alembic to use the SQLAlchemy engine from src.models,
supporting both offline (SQL generation) and online (live DB) migrations.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the project root is on sys.path so src.models can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.models import Base  # noqa: E402

# Alembic Config object (provides access to alembic.ini values)
config = context.config

# Set up Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def get_url() -> str:
    """Resolve the database URL from environment, falling back to alembic.ini."""
    return os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without requiring a live database connection.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an engine and associates a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
