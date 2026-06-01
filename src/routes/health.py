"""Health check endpoint for the PickUp AI IVR Receptionist.

Returns JSON with status of database and Redis connectivity.
Used by Docker Compose health checks and the deploy script to verify
the application is ready to serve traffic.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health_check():
    """GET /health — Check database and Redis connectivity.

    Returns HTTP 200 with {"status": "healthy"} when all dependencies are up.
    Returns HTTP 503 with {"status": "unhealthy"} when any dependency is down.
    """
    db_status = _check_database()
    redis_status = _check_redis()

    all_healthy = db_status == "connected" and redis_status == "connected"

    payload = {
        "status": "healthy" if all_healthy else "unhealthy",
        "database": db_status,
        "redis": redis_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    status_code = 200 if all_healthy else 503
    return jsonify(payload), status_code


def _check_database() -> str:
    """Attempt SELECT 1 via SQLAlchemy engine. Returns 'connected' or 'disconnected'."""
    try:
        from models import engine

        if engine is None:
            return "disconnected"

        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "connected"
    except Exception:
        return "disconnected"


def _check_redis() -> str:
    """Attempt redis.ping(). Returns 'connected' or 'disconnected'."""
    try:
        from session_store import session_store

        session_store._redis.ping()
        return "connected"
    except Exception:
        return "disconnected"
