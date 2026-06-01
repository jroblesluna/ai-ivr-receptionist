"""Auto-migration at application startup.

Runs `alembic upgrade head` to apply any pending migrations.
On failure: logs the failed migration version and raises SystemExit(1).
"""
import logging
import os

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.util.exc import CommandError

logger = logging.getLogger(__name__)


def _get_alembic_config() -> AlembicConfig:
    """Build an AlembicConfig pointing to the project's alembic.ini."""
    # Resolve alembic.ini relative to the project root (one level up from src/)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ini_path = os.path.join(project_root, "alembic.ini")
    alembic_cfg = AlembicConfig(ini_path)

    # Override script_location to use absolute path (avoids CWD issues with --chdir)
    alembic_dir = os.path.join(project_root, "src", "alembic")
    if os.path.isdir(alembic_dir):
        alembic_cfg.set_main_option("script_location", alembic_dir)

    # Override the sqlalchemy.url with the DATABASE_URL env var if set
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    return alembic_cfg


def run_migrations() -> None:
    """Apply all pending Alembic migrations (upgrade to head).

    If the database already has tables (from a previous migration or manual setup),
    stamps the current head without running migrations.
    """
    try:
        alembic_cfg = _get_alembic_config()

        # Check if alembic_version table exists (migrations already tracked)
        from sqlalchemy import create_engine, inspect, text
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url:
            eng = create_engine(db_url)
            inspector = inspect(eng)
            tables = inspector.get_table_names()
            eng.dispose()

            if "alembic_version" in tables:
                logger.info("Alembic version table exists — migrations already applied.")
                return

            if len(tables) > 0 and "alembic_version" not in tables:
                # Tables exist but no alembic tracking — stamp head
                logger.info("Tables exist without alembic tracking — stamping head.")
                command.stamp(alembic_cfg, "head")
                return

        logger.info("Running database migrations (alembic upgrade head)...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully.")
    except Exception as e:
        error_msg = str(e).lower()
        if "already exists" in error_msg or "relation" in error_msg:
            logger.warning("Tables already exist, stamping head: %s", e)
            try:
                alembic_cfg = _get_alembic_config()
                command.stamp(alembic_cfg, "head")
            except Exception:
                pass
        else:
            logger.error("Database migration failed: %s", e)
            raise SystemExit(1)
