"""Unit tests for src/realtime/stt.py DeepgramSTTClient."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.realtime.stt import (
    DEFAULT_CHANNELS,
    DEFAULT_ENCODING,
    DEFAULT_ENDPOINTING_MS,
    DEFAULT_SAMPLE_RATE,
    MAX_RECONNECT_ATTEMPTS,
    RECONNECT_TIMEOUT_SECONDS,
    DeepgramSTTClient,
)


@pytest.fixture
def mock_deepgram_connection():
    """Create a mock Deepgram live connection."""
    conn = AsyncMock()
    conn.on = MagicMock()
    conn.start_listening = AsyncMock()
    conn.send = AsyncMock()
    conn.__aexit__ = AsyncMock()
    return conn


@pytest.fixture
def mock_deepgram_client(mock_deepgram_connection):
    """Create a mock AsyncDeepgramClient with live connection support."""
    client = MagicMock()

    # Mock the context manager chain: client.listen.v1.connect(...)
    connect_cm = AsyncMock()
    connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
    connect_cm.__aexit__ = AsyncMock(return_value=False)

    client.listen.v1.connect = MagicMock(return_value=connect_cm)
    return client


class TestDeepgramSTTClientInit:
    """Tests for DeepgramSTTClient initialization."""

    @patch("src.realtime.stt.AsyncDeepgramClient")
    def test_creates_client_with_api_key(self, mock_client_cls):
        """Client is created with DEEPGRAM_API_KEY from environment."""
        with patch.dict("os.environ", {"DEEPGRAM_API_KEY": "test_key_123"}):
            stt = DeepgramSTTClient()
            mock_client_cls.assert_called_once_with(api_key="test_key_123")

    @patch("src.realtime.stt.AsyncDeepgramClient")
    def test_creates_client_with_empty_key_when_missing(self, mock_client_cls):
        """Client is created with empty string when env var is missing."""
        with patch.dict("os.environ", {}, clear=True):
            stt = DeepgramSTTClient()
            mock_client_cls.assert_called_once_with(api_key="")

    @patch("src.realtime.stt.AsyncDeepgramClient")
    def test_initial_state(self, mock_client_cls):
        """Client starts in disconnected state with no callbacks."""
        stt = DeepgramSTTClient()
        assert stt.is_connected is False
        assert stt._transcript_callbacks == []
        assert stt._connection is None


class TestDeepgramSTTClientConnect:
    """Tests for the connect() method."""

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_connect_with_default_params(self, mock_client_cls, mock_deepgram_connection):
        """connect() opens WebSocket with default mulaw/8000/1 config."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        await stt.connect()

        mock_client_cls.return_value.listen.v1.connect.assert_called_once_with(
            model="nova-3",
            encoding=DEFAULT_ENCODING,
            sample_rate=DEFAULT_SAMPLE_RATE,
            channels=DEFAULT_CHANNELS,
            interim_results=True,
            endpointing=DEFAULT_ENDPOINTING_MS,
        )
        assert stt.is_connected is True

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_connect_with_custom_params(self, mock_client_cls, mock_deepgram_connection):
        """connect() passes custom encoding/sample_rate/channels."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        await stt.connect(encoding="linear16", sample_rate=16000, channels=2)

        mock_client_cls.return_value.listen.v1.connect.assert_called_once_with(
            model="nova-3",
            encoding="linear16",
            sample_rate=16000,
            channels=2,
            interim_results=True,
            endpointing=DEFAULT_ENDPOINTING_MS,
        )

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_connect_registers_event_handlers(self, mock_client_cls, mock_deepgram_connection):
        """connect() registers MESSAGE, ERROR, and CLOSE event handlers."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        await stt.connect()

        # Verify event handlers were registered
        assert mock_deepgram_connection.on.call_count == 3

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_connect_starts_listening(self, mock_client_cls, mock_deepgram_connection):
        """connect() calls start_listening() on the connection."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        await stt.connect()

        mock_deepgram_connection.start_listening.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_connect_failure_sets_disconnected(self, mock_client_cls):
        """connect() sets is_connected=False on failure."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(side_effect=ConnectionError("Network error"))
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        with pytest.raises(ConnectionError):
            await stt.connect()

        assert stt.is_connected is False


class TestDeepgramSTTClientSendAudio:
    """Tests for the send_audio() method."""

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_send_audio_forwards_bytes(self, mock_client_cls, mock_deepgram_connection):
        """send_audio() forwards raw bytes to the Deepgram connection."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        await stt.connect()

        audio = b"\x80\x81\x82\x83"
        await stt.send_audio(audio)

        mock_deepgram_connection.send.assert_called_once_with(audio)

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_send_audio_raises_when_not_connected(self, mock_client_cls):
        """send_audio() raises RuntimeError if not connected."""
        stt = DeepgramSTTClient()

        with pytest.raises(RuntimeError, match="STT connection not established"):
            await stt.send_audio(b"\x00\x01")

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_send_audio_marks_disconnected_on_error(self, mock_client_cls, mock_deepgram_connection):
        """send_audio() sets is_connected=False when send fails."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)
        mock_deepgram_connection.send = AsyncMock(side_effect=Exception("WS closed"))

        stt = DeepgramSTTClient()
        await stt.connect()
        assert stt.is_connected is True

        with pytest.raises(Exception, match="WS closed"):
            await stt.send_audio(b"\x00")

        assert stt.is_connected is False


class TestDeepgramSTTClientCallbacks:
    """Tests for transcript callback registration and invocation."""

    @patch("src.realtime.stt.AsyncDeepgramClient")
    def test_on_transcript_registers_callback(self, mock_client_cls):
        """on_transcript() adds callback to the list."""
        stt = DeepgramSTTClient()
        callback = AsyncMock()
        stt.on_transcript(callback)

        assert callback in stt._transcript_callbacks

    @patch("src.realtime.stt.AsyncDeepgramClient")
    def test_multiple_callbacks_registered(self, mock_client_cls):
        """Multiple callbacks can be registered."""
        stt = DeepgramSTTClient()
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        stt.on_transcript(cb1)
        stt.on_transcript(cb2)

        assert len(stt._transcript_callbacks) == 2

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_handle_message_invokes_callbacks_with_object_response(self, mock_client_cls):
        """_handle_message invokes callbacks with transcript from object-style response."""
        stt = DeepgramSTTClient()
        callback = AsyncMock()
        stt.on_transcript(callback)

        # Simulate an object-style message from Deepgram SDK
        message = MagicMock()
        alt = MagicMock()
        alt.transcript = "hello world"
        message.channel.alternatives = [alt]
        message.is_final = True

        await stt._handle_message(message)

        callback.assert_called_once_with("hello world", True)

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_handle_message_invokes_callbacks_with_dict_response(self, mock_client_cls):
        """_handle_message invokes callbacks with transcript from dict-style response."""
        stt = DeepgramSTTClient()
        callback = AsyncMock()
        stt.on_transcript(callback)

        # Simulate a dict-style message
        message = {
            "channel": {
                "alternatives": [{"transcript": "testing one two"}]
            },
            "is_final": False,
        }

        await stt._handle_message(message)

        callback.assert_called_once_with("testing one two", False)

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_handle_message_skips_empty_transcript(self, mock_client_cls):
        """_handle_message does not invoke callbacks for empty transcripts."""
        stt = DeepgramSTTClient()
        callback = AsyncMock()
        stt.on_transcript(callback)

        message = MagicMock()
        alt = MagicMock()
        alt.transcript = ""
        message.channel.alternatives = [alt]
        message.is_final = False

        await stt._handle_message(message)

        callback.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_handle_message_callback_error_does_not_crash(self, mock_client_cls):
        """A failing callback does not prevent other callbacks from running."""
        stt = DeepgramSTTClient()
        failing_cb = AsyncMock(side_effect=ValueError("oops"))
        good_cb = AsyncMock()
        stt.on_transcript(failing_cb)
        stt.on_transcript(good_cb)

        message = MagicMock()
        alt = MagicMock()
        alt.transcript = "test"
        message.channel.alternatives = [alt]
        message.is_final = True

        await stt._handle_message(message)

        # Both callbacks were called despite the first one failing
        failing_cb.assert_called_once_with("test", True)
        good_cb.assert_called_once_with("test", True)


class TestDeepgramSTTClientReconnect:
    """Tests for the reconnect() method."""

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_reconnect_success_on_first_attempt(self, mock_client_cls, mock_deepgram_connection):
        """reconnect() returns True when connection succeeds on first try."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        result = await stt.reconnect()

        assert result is True
        assert stt.is_connected is True

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_reconnect_returns_false_after_max_attempts(self, mock_client_cls):
        """reconnect() returns False after MAX_RECONNECT_ATTEMPTS failures."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        result = await stt.reconnect()

        assert result is False
        assert stt.is_connected is False

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_reconnect_respects_timeout(self, mock_client_cls):
        """reconnect() times out after RECONNECT_TIMEOUT_SECONDS per attempt."""
        async def slow_connect(*args, **kwargs):
            await asyncio.sleep(10)  # Much longer than timeout

        connect_cm = AsyncMock()
        connect_cm.__aenter__ = slow_connect
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        result = await stt.reconnect()

        assert result is False


class TestDeepgramSTTClientClose:
    """Tests for the close() method."""

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_close_cleans_up_connection(self, mock_client_cls, mock_deepgram_connection):
        """close() closes the connection and clears callbacks."""
        connect_cm = AsyncMock()
        connect_cm.__aenter__ = AsyncMock(return_value=mock_deepgram_connection)
        mock_client_cls.return_value.listen.v1.connect = MagicMock(return_value=connect_cm)

        stt = DeepgramSTTClient()
        await stt.connect()
        stt.on_transcript(AsyncMock())

        await stt.close()

        assert stt.is_connected is False
        assert stt._transcript_callbacks == []
        assert stt._connection is None

    @pytest.mark.asyncio
    @patch("src.realtime.stt.AsyncDeepgramClient")
    async def test_close_when_not_connected(self, mock_client_cls):
        """close() is safe to call when not connected."""
        stt = DeepgramSTTClient()
        await stt.close()  # Should not raise

        assert stt.is_connected is False


class TestConstants:
    """Tests for module-level constants."""

    def test_reconnect_timeout(self):
        assert RECONNECT_TIMEOUT_SECONDS == 2.0

    def test_max_reconnect_attempts(self):
        assert MAX_RECONNECT_ATTEMPTS == 2

    def test_default_encoding(self):
        assert DEFAULT_ENCODING == "mulaw"

    def test_default_sample_rate(self):
        assert DEFAULT_SAMPLE_RATE == 8000

    def test_default_channels(self):
        assert DEFAULT_CHANNELS == 1

    def test_default_endpointing(self):
        assert DEFAULT_ENDPOINTING_MS == 300
