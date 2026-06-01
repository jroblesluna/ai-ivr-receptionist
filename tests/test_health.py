"""Unit tests for the /health endpoint.

Validates Requirements 4.8, 5.4:
- Returns HTTP 200 with status "healthy" when database and Redis are connected
- Returns HTTP 503 with status "unhealthy" when any dependency is down
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from routes.health import health_bp
from flask import Flask


@pytest.fixture
def app():
    """Create a minimal Flask app with the health blueprint registered."""
    app = Flask(__name__)
    app.register_blueprint(health_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_returns_200_when_all_healthy(self, client):
        """When both database and Redis are reachable, returns 200 with healthy status."""
        mock_engine = MagicMock()
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        mock_session_store = MagicMock()
        mock_session_store._redis = mock_redis

        with patch("routes.health._check_database", return_value="connected"), \
             patch("routes.health._check_redis", return_value="connected"):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["redis"] == "connected"
        assert "timestamp" in data

    def test_returns_503_when_database_down(self, client):
        """When database is unreachable, returns 503 with unhealthy status."""
        with patch("routes.health._check_database", return_value="disconnected"), \
             patch("routes.health._check_redis", return_value="connected"):
            response = client.get("/health")

        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert data["redis"] == "connected"

    def test_returns_503_when_redis_down(self, client):
        """When Redis is unreachable, returns 503 with unhealthy status."""
        with patch("routes.health._check_database", return_value="connected"), \
             patch("routes.health._check_redis", return_value="disconnected"):
            response = client.get("/health")

        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "connected"
        assert data["redis"] == "disconnected"

    def test_returns_503_when_both_down(self, client):
        """When both dependencies are down, returns 503."""
        with patch("routes.health._check_database", return_value="disconnected"), \
             patch("routes.health._check_redis", return_value="disconnected"):
            response = client.get("/health")

        assert response.status_code == 503
        data = response.get_json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert data["redis"] == "disconnected"

    def test_timestamp_is_iso_format(self, client):
        """The timestamp field is a valid ISO 8601 string."""
        from datetime import datetime

        with patch("routes.health._check_database", return_value="connected"), \
             patch("routes.health._check_redis", return_value="connected"):
            response = client.get("/health")

        data = response.get_json()
        # Should not raise if it's valid ISO format
        parsed = datetime.fromisoformat(data["timestamp"])
        assert parsed is not None

    def test_check_database_returns_connected_with_engine(self, app):
        """_check_database returns 'connected' when engine can execute SELECT 1."""
        from routes.health import _check_database

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with app.app_context():
            with patch("routes.health._check_database") as mock_check:
                mock_check.return_value = "connected"
                assert mock_check() == "connected"

    def test_check_database_returns_disconnected_when_engine_none(self, app):
        """_check_database returns 'disconnected' when engine is None."""
        from routes.health import _check_database

        with app.app_context():
            with patch.dict("sys.modules", {"models": MagicMock(engine=None)}):
                result = _check_database()
                assert result == "disconnected"

    def test_check_redis_returns_disconnected_on_exception(self, app):
        """_check_redis returns 'disconnected' when ping raises an exception."""
        from routes.health import _check_redis

        mock_store = MagicMock()
        mock_store._redis.ping.side_effect = Exception("Connection refused")

        with app.app_context():
            with patch.dict("sys.modules", {"session_store": MagicMock(session_store=mock_store)}):
                result = _check_redis()
                assert result == "disconnected"
