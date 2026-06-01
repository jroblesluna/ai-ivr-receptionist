"""
SQLAlchemy models package for PickUp AI IVR Receptionist.

Provides:
- Base declarative class
- Engine factory with connection pooling
- Session factory
- Startup retry logic with exponential backoff
"""
import logging
import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# Module-level engine and session factory (initialized via init_db)
engine = None
Session = None


def get_database_url() -> str:
    """Resolve the database URL from environment."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url


def create_engine_with_pool(database_url: str):
    """Create a SQLAlchemy engine with connection pooling configuration."""
    return create_engine(
        database_url,
        pool_size=2,
        max_overflow=8,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


def init_db(database_url: str | None = None, max_retries: int = 3):
    """
    Initialize the database engine and session factory with startup retry logic.

    Uses exponential backoff: 1s → 2s → 4s (3 attempts max).
    On failure after all retries: logs error and raises SystemExit(1).
    """
    global engine, Session

    if database_url is None:
        database_url = get_database_url()

    backoff = 1  # initial backoff in seconds

    for attempt in range(1, max_retries + 1):
        try:
            engine = create_engine_with_pool(database_url)
            # Verify the connection is reachable
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Session = sessionmaker(bind=engine)
            logger.info("Database connection established successfully.")
            return
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "Database connection attempt %d/%d failed: %s. "
                    "Retrying in %ds...",
                    attempt, max_retries, e, backoff,
                )
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error(
                    "Database connection failed after %d attempts: %s",
                    max_retries, e,
                )
                raise SystemExit(1)


# Import all models so they are registered with Base.metadata
try:
    from src.models.config import Config  # noqa: E402, F401
    from src.models.report import Report  # noqa: E402, F401
    from src.models.use_case import UseCase, Topic  # noqa: E402, F401
    from src.models.user import Role, User, UserUseCase  # noqa: E402, F401
    from src.models.caller_profile import CallerProfile  # noqa: E402, F401
except ImportError:
    from models.config import Config  # noqa: E402, F401
    from models.report import Report  # noqa: E402, F401
    from models.use_case import UseCase, Topic  # noqa: E402, F401
    from models.user import Role, User, UserUseCase  # noqa: E402, F401
    from models.caller_profile import CallerProfile  # noqa: E402, F401

__all__ = [
    "Base",
    "engine",
    "Session",
    "init_db",
    "get_database_url",
    "create_engine_with_pool",
    "Config",
    "Report",
    "UseCase",
    "Topic",
    "Role",
    "User",
    "UserUseCase",
    "CallerProfile",
]
