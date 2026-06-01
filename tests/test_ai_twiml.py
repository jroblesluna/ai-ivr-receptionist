"""Unit tests for TwiML generation in ai.py — Connect/Stream for conversational demos."""

import os
import sys
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Mock heavy dependencies before importing routes.ai
# runtime_config triggers db.config_seed which needs DATABASE_URL
_mock_runtime_config = MagicMock()
_mock_runtime_config.get = MagicMock(return_value="")
sys.modules.setdefault("runtime_config", _mock_runtime_config)

_mock_db = MagicMock()
sys.modules.setdefault("db", _mock_db)

_mock_session_store_module = MagicMock()
sys.modules.setdefault("session_store", _mock_session_store_module)

_mock_use_case_loader = MagicMock()
sys.modules.setdefault("use_case_loader", _mock_use_case_loader)

_mock_helpers = MagicMock()
_mock_helpers.get_voice = MagicMock(return_value="alice")
_mock_helpers.get_gather_language = MagicMock(return_value="en-US")
sys.modules.setdefault("helpers", _mock_helpers)

_mock_prompts = MagicMock()
sys.modules.setdefault("prompts", _mock_prompts)

_mock_email_helper = MagicMock()
sys.modules.setdefault("email_helper", _mock_email_helper)

_mock_config = MagicMock()
sys.modules.setdefault("config", _mock_config)

_mock_reports = MagicMock()
sys.modules.setdefault("reports", _mock_reports)

# Now import the module under test
from routes.ai import _build_media_stream_twiml, _check_media_stream_health
import routes.ai as ai_module


class TestBuildMediaStreamTwiml:
    """Tests for _build_media_stream_twiml helper."""

    def test_generates_connect_stream_element(self):
        """TwiML contains <Connect><Stream> with correct URL."""
        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = "example.com"
        try:
            result = _build_media_stream_twiml(
                lang="en",
                demo_id="demo_123",
                caller_from="+14085551234",
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        assert root.tag == "Response"

        connect = root.find("Connect")
        assert connect is not None

        stream = connect.find("Stream")
        assert stream is not None
        assert stream.get("url") == "wss://example.com/media-stream"

    def test_passes_custom_parameters(self):
        """TwiML contains Parameter elements for lang, demo_id, caller_from."""
        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = "test.example.com"
        try:
            result = _build_media_stream_twiml(
                lang="es",
                demo_id="demo_456",
                caller_from="+15551234567",
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        stream = root.find("Connect/Stream")
        params = stream.findall("Parameter")

        param_dict = {p.get("name"): p.get("value") for p in params}
        assert param_dict["lang"] == "es"
        assert param_dict["demo_id"] == "demo_456"
        assert param_dict["caller_from"] == "+15551234567"

    def test_no_gather_element_present(self):
        """TwiML for media stream does NOT contain a <Gather> element."""
        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = "ws.example.com"
        try:
            result = _build_media_stream_twiml(
                lang="en",
                demo_id="demo_789",
                caller_from="+10000000000",
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        assert root.find("Gather") is None

    def test_three_parameters_present(self):
        """Exactly 3 parameters are passed: lang, demo_id, caller_from."""
        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = "host.test"
        try:
            result = _build_media_stream_twiml(
                lang="en",
                demo_id="d1",
                caller_from="+1",
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        params = root.findall("Connect/Stream/Parameter")
        assert len(params) == 3


class TestCheckMediaStreamHealth:
    """Tests for _check_media_stream_health helper."""

    @patch("routes.ai.http_requests.get")
    def test_returns_true_on_200(self, mock_get):
        """Returns True when health endpoint responds with 200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert _check_media_stream_health() is True
        mock_get.assert_called_once_with("http://localhost:8001/health", timeout=2)

    @patch("routes.ai.http_requests.get")
    def test_returns_false_on_500(self, mock_get):
        """Returns False when health endpoint responds with non-200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        assert _check_media_stream_health() is False

    @patch("routes.ai.http_requests.get")
    def test_returns_false_on_connection_error(self, mock_get):
        """Returns False when health endpoint is unreachable."""
        mock_get.side_effect = ConnectionError("Connection refused")

        assert _check_media_stream_health() is False

    @patch("routes.ai.http_requests.get")
    def test_returns_false_on_timeout(self, mock_get):
        """Returns False when health endpoint times out."""
        mock_get.side_effect = OSError("Timed out")

        assert _check_media_stream_health() is False
