"""Unit tests for src/realtime/server.py.

Tests the FastAPI WebSocket server handling of Twilio Media Stream events
including connected, start, media, and stop events, as well as the health
check endpoint and disconnect detection.
"""

from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.realtime.server import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Health Check Tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Tests for the /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# WebSocket Event Handling Tests
# ---------------------------------------------------------------------------


class TestWebSocketEndpoint:
    """Tests for the /media-stream WebSocket endpoint."""

    def _make_connected_msg(self) -> str:
        return json.dumps({
            "event": "connected",
            "protocol": "Call",
            "version": "1.0.0",
        })

    def _make_start_msg(
        self,
        call_sid: str = "CA123",
        stream_sid: str = "MZ456",
        lang: str = "en",
        demo_id: str = "demo_1",
        caller_from: str = "+14085551234",
    ) -> str:
        return json.dumps({
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "streamSid": stream_sid,
                "accountSid": "AC000",
                "callSid": call_sid,
                "customParameters": {
                    "lang": lang,
                    "demo_id": demo_id,
                    "caller_from": caller_from,
                },
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1,
                },
            },
            "streamSid": stream_sid,
        })

    def _make_media_msg(self, stream_sid: str = "MZ456", payload: bytes = b"\x00\x01\x02") -> str:
        return json.dumps({
            "event": "media",
            "sequenceNumber": "4",
            "media": {
                "track": "inbound",
                "chunk": "2",
                "timestamp": "5",
                "payload": base64.b64encode(payload).decode(),
            },
            "streamSid": stream_sid,
        })

    def _make_stop_msg(self, stream_sid: str = "MZ456") -> str:
        return json.dumps({
            "event": "stop",
            "sequenceNumber": "100",
            "streamSid": stream_sid,
        })

    @pytest.mark.asyncio
    @patch("src.realtime.server.ConversationSession")
    async def test_start_event_initializes_session(self, mock_session_cls):
        """Start event should create and initialize a ConversationSession."""
        mock_session = AsyncMock()
        mock_session.call_sid = "CA123"
        mock_session.stream_sid = "MZ456"
        mock_session.language = "en"
        mock_session.demo_id = "demo_1"
        mock_session.caller_from = "+14085551234"
        mock_session.stt_client = None
        mock_session.vad_processor = None
        mock_session_cls.return_value = mock_session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream("GET", "/media-stream") as _:
                pass  # WebSocket test needs different approach

        # Use the starlette test client for WebSocket testing
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/media-stream") as ws:
                ws.send_text(self._make_connected_msg())
                ws.send_text(self._make_start_msg())
                ws.send_text(self._make_stop_msg())

        mock_session_cls.assert_called_once_with(
            call_sid="CA123",
            stream_sid="MZ456",
            language="en",
            demo_id="demo_1",
            caller_from="+14085551234",
            voice_id="pNInz6obpgDQGcFmaJgB",
        )
        mock_session.initialize.assert_awaited_once()
        mock_session.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.realtime.server.ConversationSession")
    async def test_media_event_forwards_to_stt_and_vad(self, mock_session_cls):
        """Media event should decode payload and forward to STT and VAD."""
        mock_stt = AsyncMock()
        mock_vad = MagicMock()

        mock_session = AsyncMock()
        mock_session.call_sid = "CA123"
        mock_session.stream_sid = "MZ456"
        mock_session.language = "en"
        mock_session.demo_id = "demo_1"
        mock_session.caller_from = "+14085551234"
        mock_session.stt_client = mock_stt
        mock_session.vad_processor = mock_vad
        mock_session_cls.return_value = mock_session

        audio_payload = b"\x80\x81\x82\x83"

        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/media-stream") as ws:
                ws.send_text(self._make_connected_msg())
                ws.send_text(self._make_start_msg())
                ws.send_text(self._make_media_msg(payload=audio_payload))
                ws.send_text(self._make_stop_msg())

        # Verify STT received the audio
        mock_stt.send_audio.assert_awaited_with(audio_payload)
        # Verify VAD received the audio
        mock_vad.process_frame.assert_called_with(audio_payload)

    @pytest.mark.asyncio
    @patch("src.realtime.server.ConversationSession")
    async def test_stop_event_triggers_cleanup(self, mock_session_cls):
        """Stop event should trigger session cleanup."""
        mock_session = AsyncMock()
        mock_session.call_sid = "CA123"
        mock_session.stream_sid = "MZ456"
        mock_session.language = "en"
        mock_session.demo_id = "demo_1"
        mock_session.caller_from = "+14085551234"
        mock_session.stt_client = None
        mock_session.vad_processor = None
        mock_session_cls.return_value = mock_session

        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/media-stream") as ws:
                ws.send_text(self._make_connected_msg())
                ws.send_text(self._make_start_msg())
                ws.send_text(self._make_stop_msg())

        mock_session.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.realtime.server.ConversationSession")
    async def test_disconnect_triggers_cleanup(self, mock_session_cls):
        """WebSocket disconnect should trigger session cleanup."""
        mock_session = AsyncMock()
        mock_session.call_sid = "CA123"
        mock_session.stream_sid = "MZ456"
        mock_session.language = "en"
        mock_session.demo_id = "demo_1"
        mock_session.caller_from = "+14085551234"
        mock_session.stt_client = None
        mock_session.vad_processor = None
        mock_session_cls.return_value = mock_session

        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/media-stream") as ws:
                ws.send_text(self._make_connected_msg())
                ws.send_text(self._make_start_msg())
                # Close without sending stop — simulates disconnect

        mock_session.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.realtime.server.ConversationSession")
    async def test_media_without_start_is_ignored(self, mock_session_cls):
        """Media events before start should be ignored (no session yet)."""
        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/media-stream") as ws:
                ws.send_text(self._make_connected_msg())
                # Send media before start — should not crash
                ws.send_text(self._make_media_msg())
                ws.send_text(self._make_stop_msg())

        # No session was created, so no calls should have been made
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.realtime.server.ConversationSession")
    async def test_custom_parameters_extracted(self, mock_session_cls):
        """Custom parameters (lang, demo_id, caller_from) should be extracted from start event."""
        mock_session = AsyncMock()
        mock_session.call_sid = "CA999"
        mock_session.stream_sid = "MZ888"
        mock_session.language = "es"
        mock_session.demo_id = "demo_xyz"
        mock_session.caller_from = "+34600111222"
        mock_session.stt_client = None
        mock_session.vad_processor = None
        mock_session_cls.return_value = mock_session

        from starlette.testclient import TestClient

        with TestClient(app) as client:
            with client.websocket_connect("/media-stream") as ws:
                ws.send_text(self._make_connected_msg())
                ws.send_text(self._make_start_msg(
                    call_sid="CA999",
                    stream_sid="MZ888",
                    lang="es",
                    demo_id="demo_xyz",
                    caller_from="+34600111222",
                ))
                ws.send_text(self._make_stop_msg(stream_sid="MZ888"))

        mock_session_cls.assert_called_once_with(
            call_sid="CA999",
            stream_sid="MZ888",
            language="es",
            demo_id="demo_xyz",
            caller_from="+34600111222",
            voice_id="pNInz6obpgDQGcFmaJgB",
        )
