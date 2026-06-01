"""Unit tests for src/realtime/tts.py ElevenLabsTTSClient."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.realtime.tts import (
    DEFAULT_MODEL_ID,
    OUTPUT_FORMAT,
    ElevenLabsTTSClient,
    _API_BASE_URL,
    _STREAM_CHUNK_SIZE,
)


@pytest.fixture
def tts_client():
    """Create a TTS client with test API key and default voice."""
    with patch.dict("os.environ", {
        "ELEVENLABS_API_KEY": "test_api_key",
        "DEFAULT_ELEVENLABS_VOICE_ID": "default_voice_123",
    }):
        client = ElevenLabsTTSClient()
    return client


@pytest.fixture
def tts_client_no_default_voice():
    """Create a TTS client without a default voice ID."""
    with patch.dict("os.environ", {
        "ELEVENLABS_API_KEY": "test_api_key",
        "DEFAULT_ELEVENLABS_VOICE_ID": "",
    }):
        client = ElevenLabsTTSClient()
    return client


class TestElevenLabsTTSClientInit:
    """Tests for ElevenLabsTTSClient initialization."""

    def test_uses_env_api_key(self):
        """Client reads ELEVENLABS_API_KEY from environment."""
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": "sk_test_key"}):
            client = ElevenLabsTTSClient()
            assert client._api_key == "sk_test_key"

    def test_uses_explicit_api_key(self):
        """Explicit api_key parameter overrides environment."""
        client = ElevenLabsTTSClient(api_key="explicit_key")
        assert client._api_key == "explicit_key"

    def test_uses_env_default_voice_id(self):
        """Client reads DEFAULT_ELEVENLABS_VOICE_ID from environment."""
        with patch.dict("os.environ", {"DEFAULT_ELEVENLABS_VOICE_ID": "voice_abc"}):
            client = ElevenLabsTTSClient()
            assert client._default_voice_id == "voice_abc"

    def test_default_model_id(self):
        """Client uses eleven_flash_v2_5 model by default."""
        client = ElevenLabsTTSClient()
        assert client._model_id == DEFAULT_MODEL_ID

    def test_custom_model_id(self):
        """Custom model_id parameter is stored."""
        client = ElevenLabsTTSClient(model_id="eleven_multilingual_v2")
        assert client._model_id == "eleven_multilingual_v2"


class TestResolveVoiceId:
    """Tests for voice ID resolution with fallback."""

    def test_uses_provided_voice_id(self, tts_client):
        """When voice_id is provided, it is used directly."""
        assert tts_client._resolve_voice_id("custom_voice") == "custom_voice"

    def test_falls_back_to_default_when_empty(self, tts_client):
        """When voice_id is empty string, falls back to default."""
        assert tts_client._resolve_voice_id("") == "default_voice_123"

    def test_falls_back_to_default_when_none(self, tts_client):
        """When voice_id is None, falls back to default."""
        assert tts_client._resolve_voice_id(None) == "default_voice_123"

    def test_returns_empty_when_no_default(self, tts_client_no_default_voice):
        """When no default voice configured and voice_id is empty, returns empty."""
        assert tts_client_no_default_voice._resolve_voice_id("") == ""


class TestSynthesizeStream:
    """Tests for the synthesize_stream() method."""

    @pytest.mark.asyncio
    async def test_skips_empty_text(self, tts_client):
        """synthesize_stream does nothing for empty text."""
        callback = AsyncMock()
        await tts_client.synthesize_stream("", "voice_id", callback)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_whitespace_only_text(self, tts_client):
        """synthesize_stream does nothing for whitespace-only text."""
        callback = AsyncMock()
        await tts_client.synthesize_stream("   ", "voice_id", callback)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_none_text(self, tts_client):
        """synthesize_stream does nothing for None text."""
        callback = AsyncMock()
        await tts_client.synthesize_stream(None, "voice_id", callback)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_error_when_no_voice_id_available(self, tts_client_no_default_voice):
        """synthesize_stream logs error and returns when no voice ID is available."""
        callback = AsyncMock()
        await tts_client_no_default_voice.synthesize_stream("Hello", "", callback)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_streams_audio_chunks_to_callback(self, tts_client):
        """synthesize_stream forwards audio chunks from API to callback."""
        chunks = [b"\x80\x81\x82", b"\x83\x84\x85", b"\x86\x87"]
        callback = AsyncMock()

        # Mock the httpx streaming response
        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes(chunk_size=None):
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        # Create async context manager mock
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(tts_client._http_client, "stream", return_value=mock_stream_cm):
            await tts_client.synthesize_stream("Hello world", "voice_123", callback)

        assert callback.call_count == 3
        callback.assert_any_call(b"\x80\x81\x82")
        callback.assert_any_call(b"\x83\x84\x85")
        callback.assert_any_call(b"\x86\x87")

    @pytest.mark.asyncio
    async def test_uses_correct_api_url(self, tts_client):
        """synthesize_stream calls the correct ElevenLabs streaming endpoint."""
        callback = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes(chunk_size=None):
            yield b"\x00"

        mock_response.aiter_bytes = mock_aiter_bytes

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(tts_client._http_client, "stream", return_value=mock_stream_cm) as mock_stream:
            await tts_client.synthesize_stream("Test", "my_voice", callback)

            mock_stream.assert_called_once_with(
                "POST",
                f"{_API_BASE_URL}/text-to-speech/my_voice/stream",
                headers={
                    "xi-api-key": "test_api_key",
                    "Content-Type": "application/json",
                },
                json={
                    "text": "Test",
                    "model_id": DEFAULT_MODEL_ID,
                },
                params={
                    "output_format": OUTPUT_FORMAT,
                },
            )

    @pytest.mark.asyncio
    async def test_uses_fallback_voice_id(self, tts_client):
        """synthesize_stream uses default voice when voice_id is empty."""
        callback = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes(chunk_size=None):
            yield b"\x00"

        mock_response.aiter_bytes = mock_aiter_bytes

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(tts_client._http_client, "stream", return_value=mock_stream_cm) as mock_stream:
            await tts_client.synthesize_stream("Test", "", callback)

            # Should use the default voice ID in the URL
            call_args = mock_stream.call_args
            assert "default_voice_123" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_handles_api_error_response(self, tts_client):
        """synthesize_stream logs error and returns on non-200 response."""
        callback = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.aread = AsyncMock(return_value=b'{"error": "unauthorized"}')

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(tts_client._http_client, "stream", return_value=mock_stream_cm):
            # Should not raise
            await tts_client.synthesize_stream("Hello", "voice_123", callback)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_network_error(self, tts_client):
        """synthesize_stream logs error and returns on network failure."""
        callback = AsyncMock()

        with patch.object(
            tts_client._http_client,
            "stream",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            # Should not raise — error is logged and skipped
            await tts_client.synthesize_stream("Hello", "voice_123", callback)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_timeout_error(self, tts_client):
        """synthesize_stream logs error and returns on timeout."""
        callback = AsyncMock()

        with patch.object(
            tts_client._http_client,
            "stream",
            side_effect=httpx.ReadTimeout("Read timed out"),
        ):
            # Should not raise
            await tts_client.synthesize_stream("Hello", "voice_123", callback)

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_error_does_not_stop_streaming(self, tts_client):
        """A failing callback does not prevent subsequent chunks from being processed."""
        chunks = [b"\x01", b"\x02", b"\x03"]
        call_count = 0

        async def flaky_callback(chunk):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Callback failed")

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes(chunk_size=None):
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(tts_client._http_client, "stream", return_value=mock_stream_cm):
            await tts_client.synthesize_stream("Hello", "voice_123", flaky_callback)

        # All 3 chunks were attempted despite first callback failing
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_skips_empty_chunks(self, tts_client):
        """synthesize_stream skips empty byte chunks from the API."""
        chunks = [b"\x01", b"", b"\x02"]
        callback = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes(chunk_size=None):
            for chunk in chunks:
                yield chunk

        mock_response.aiter_bytes = mock_aiter_bytes

        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(tts_client._http_client, "stream", return_value=mock_stream_cm):
            await tts_client.synthesize_stream("Hello", "voice_123", callback)

        # Only non-empty chunks are forwarded
        assert callback.call_count == 2
        callback.assert_any_call(b"\x01")
        callback.assert_any_call(b"\x02")


class TestClose:
    """Tests for the close() method."""

    @pytest.mark.asyncio
    async def test_close_closes_http_client(self, tts_client):
        """close() closes the underlying httpx client."""
        with patch.object(tts_client._http_client, "aclose", new_callable=AsyncMock) as mock_close:
            await tts_client.close()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_error_gracefully(self, tts_client):
        """close() does not raise even if httpx client close fails."""
        with patch.object(
            tts_client._http_client,
            "aclose",
            new_callable=AsyncMock,
            side_effect=Exception("Already closed"),
        ):
            # Should not raise
            await tts_client.close()


class TestConstants:
    """Tests for module-level constants."""

    def test_output_format(self):
        """Output format is ulaw_8000 for Twilio compatibility."""
        assert OUTPUT_FORMAT == "ulaw_8000"

    def test_default_model_id(self):
        """Default model is eleven_flash_v2_5 for low latency."""
        assert DEFAULT_MODEL_ID == "eleven_flash_v2_5"

    def test_api_base_url(self):
        """API base URL points to ElevenLabs v1 API."""
        assert _API_BASE_URL == "https://api.elevenlabs.io/v1"
