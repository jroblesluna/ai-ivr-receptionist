"""Unit tests for src/realtime/error_recovery.py.

Tests the pipeline-level error recovery strategies:
- STT failure recovery (reconnect attempts + fallback)
- LLM failure recovery (apology + retry)
- Pipeline health monitor (>5s unavailable detection)
- Conversation history preservation on fallback
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.realtime.error_recovery import (
    APOLOGY_MESSAGES,
    PIPELINE_UNAVAILABLE_TIMEOUT_S,
    PipelineHealthMonitor,
    _speak_apology,
    _trigger_fallback,
    handle_llm_failure,
    handle_stt_failure,
)
from src.realtime.models import PipelineState, SessionState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock ConversationSession with all required attributes."""
    session = MagicMock()
    session.call_sid = "CA_test_123"
    session.stream_sid = "MZ_test_456"
    session.language = "en"
    session.demo_id = "demo_test"
    session.caller_from = "+14085551234"
    session.voice_id = "voice_123"
    session.pipeline_state = PipelineState.LISTENING

    # Session state
    session.state = MagicMock()
    session.state.voice_id = "voice_123"
    session.state.conversation_history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    session.state.pipeline_state = PipelineState.LISTENING

    # STT client
    session.stt_client = AsyncMock()
    session.stt_client.reconnect = AsyncMock(return_value=True)

    # TTS client
    session.tts_client = AsyncMock()

    return session


@pytest.fixture
def mock_ws():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# STT Failure Recovery Tests
# ---------------------------------------------------------------------------


class TestSTTFailureRecovery:
    """Tests for handle_stt_failure."""

    @pytest.mark.asyncio
    async def test_stt_reconnect_success(self, mock_session, mock_ws):
        """When STT reconnects successfully, should return True."""
        mock_session.stt_client.reconnect = AsyncMock(return_value=True)

        result = await handle_stt_failure(mock_session, mock_ws)

        assert result is True
        mock_session.stt_client.reconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stt_reconnect_failure_triggers_fallback(self, mock_session, mock_ws):
        """When STT reconnect fails, should preserve history and return False."""
        mock_session.stt_client.reconnect = AsyncMock(return_value=False)

        with patch("src.realtime.error_recovery.save_conversation_history") as mock_save:
            result = await handle_stt_failure(mock_session, mock_ws)

        assert result is False
        mock_session.stt_client.reconnect.assert_awaited_once()
        # Conversation history should be preserved
        mock_save.assert_called_once_with(
            "CA_test_123",
            list(mock_session.state.conversation_history),
        )

    @pytest.mark.asyncio
    async def test_stt_client_none_triggers_fallback(self, mock_session, mock_ws):
        """When STT client is None, should trigger fallback immediately."""
        mock_session.stt_client = None

        with patch("src.realtime.error_recovery.save_conversation_history") as mock_save:
            result = await handle_stt_failure(mock_session, mock_ws)

        assert result is False
        mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# LLM Failure Recovery Tests
# ---------------------------------------------------------------------------


class TestLLMFailureRecovery:
    """Tests for handle_llm_failure."""

    @pytest.mark.asyncio
    async def test_llm_retry_success(self, mock_session, mock_ws):
        """When LLM retry succeeds, should return True."""
        messages = [{"role": "user", "content": "Hello"}]
        on_sentence_chunk = AsyncMock()
        on_complete = AsyncMock()
        cancel_event = asyncio.Event()

        with patch("src.realtime.llm.LLMStreamClient") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm

            result = await handle_llm_failure(
                session=mock_session,
                ws=mock_ws,
                messages=messages,
                on_sentence_chunk=on_sentence_chunk,
                on_complete=on_complete,
                cancel_event=cancel_event,
            )

        assert result is True
        # Apology should have been spoken via TTS
        mock_session.tts_client.synthesize_stream.assert_awaited()
        # LLM retry should have been attempted
        mock_llm.generate_response.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_retry_failure_triggers_fallback(self, mock_session, mock_ws):
        """When LLM retry also fails, should preserve history and return False."""
        messages = [{"role": "user", "content": "Hello"}]
        on_sentence_chunk = AsyncMock()
        on_complete = AsyncMock()
        cancel_event = asyncio.Event()

        with patch("src.realtime.llm.LLMStreamClient") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm.generate_response = AsyncMock(side_effect=Exception("LLM still down"))
            mock_llm_cls.return_value = mock_llm

            with patch("src.realtime.error_recovery.save_conversation_history") as mock_save:
                result = await handle_llm_failure(
                    session=mock_session,
                    ws=mock_ws,
                    messages=messages,
                    on_sentence_chunk=on_sentence_chunk,
                    on_complete=on_complete,
                    cancel_event=cancel_event,
                )

        assert result is False
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_no_retry_on_cancel(self, mock_session, mock_ws):
        """When cancel_event is set during apology, should not retry."""
        messages = [{"role": "user", "content": "Hello"}]
        on_sentence_chunk = AsyncMock()
        on_complete = AsyncMock()
        cancel_event = asyncio.Event()
        cancel_event.set()  # Already cancelled (barge-in)

        result = await handle_llm_failure(
            session=mock_session,
            ws=mock_ws,
            messages=messages,
            on_sentence_chunk=on_sentence_chunk,
            on_complete=on_complete,
            cancel_event=cancel_event,
        )

        assert result is False


# ---------------------------------------------------------------------------
# Apology Message Tests
# ---------------------------------------------------------------------------


class TestSpeakApology:
    """Tests for _speak_apology."""

    @pytest.mark.asyncio
    async def test_speaks_english_apology(self, mock_session, mock_ws):
        """Should synthesize English apology for 'en' language."""
        mock_session.language = "en"

        await _speak_apology(mock_session, mock_ws)

        mock_session.tts_client.synthesize_stream.assert_awaited_once()
        call_args = mock_session.tts_client.synthesize_stream.call_args
        assert call_args.kwargs["text"] == APOLOGY_MESSAGES["en"]

    @pytest.mark.asyncio
    async def test_speaks_spanish_apology(self, mock_session, mock_ws):
        """Should synthesize Spanish apology for 'es' language."""
        mock_session.language = "es"

        await _speak_apology(mock_session, mock_ws)

        mock_session.tts_client.synthesize_stream.assert_awaited_once()
        call_args = mock_session.tts_client.synthesize_stream.call_args
        assert call_args.kwargs["text"] == APOLOGY_MESSAGES["es"]

    @pytest.mark.asyncio
    async def test_falls_back_to_english_for_unknown_language(self, mock_session, mock_ws):
        """Should use English apology for unsupported languages."""
        mock_session.language = "fr"

        await _speak_apology(mock_session, mock_ws)

        mock_session.tts_client.synthesize_stream.assert_awaited_once()
        call_args = mock_session.tts_client.synthesize_stream.call_args
        assert call_args.kwargs["text"] == APOLOGY_MESSAGES["en"]

    @pytest.mark.asyncio
    async def test_no_crash_when_tts_unavailable(self, mock_session, mock_ws):
        """Should not crash when TTS client is None."""
        mock_session.tts_client = None

        # Should not raise
        await _speak_apology(mock_session, mock_ws)


# ---------------------------------------------------------------------------
# Pipeline Health Monitor Tests
# ---------------------------------------------------------------------------


class TestPipelineHealthMonitor:
    """Tests for PipelineHealthMonitor."""

    def test_record_success_resets_timer(self, mock_session):
        """record_success should reset the last success time."""
        monitor = PipelineHealthMonitor(mock_session)
        # Simulate time passing
        monitor._last_success_time = time.monotonic() - 10.0

        monitor.record_success()

        assert monitor.time_since_last_success() < 1.0

    def test_is_pipeline_unavailable_false_initially(self, mock_session):
        """Pipeline should not be unavailable immediately after creation."""
        monitor = PipelineHealthMonitor(mock_session)

        assert monitor.is_pipeline_unavailable() is False

    def test_is_pipeline_unavailable_true_after_timeout(self, mock_session):
        """Pipeline should be unavailable after >5s without success."""
        monitor = PipelineHealthMonitor(mock_session)
        monitor._last_success_time = time.monotonic() - (PIPELINE_UNAVAILABLE_TIMEOUT_S + 1.0)

        assert monitor.is_pipeline_unavailable() is True

    @pytest.mark.asyncio
    async def test_monitor_sets_failure_event(self, mock_session):
        """Monitor should set failure event when pipeline is unavailable >5s."""
        # Ensure conversation_history is a real list for the fallback save
        mock_session.state.conversation_history = [{"role": "user", "content": "test"}]

        monitor = PipelineHealthMonitor(mock_session)
        failure_event = asyncio.Event()

        with patch("src.realtime.error_recovery.save_conversation_history"):
            # Set last success time to well past the timeout AFTER creating monitor
            # but BEFORE starting monitoring (start_monitoring resets the time)
            await monitor.start_monitoring(failure_event)
            # Override the last success time after monitoring starts
            monitor._last_success_time = time.monotonic() - (PIPELINE_UNAVAILABLE_TIMEOUT_S + 2.0)
            # Wait for the monitor loop to detect the failure (loop checks every 1s)
            for _ in range(25):
                if failure_event.is_set():
                    break
                await asyncio.sleep(0.1)

        assert failure_event.is_set()
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_monitor_does_not_fire_when_healthy(self, mock_session):
        """Monitor should not set failure event when pipeline is healthy."""
        monitor = PipelineHealthMonitor(mock_session)
        failure_event = asyncio.Event()

        await monitor.start_monitoring(failure_event)
        # Keep recording success
        monitor.record_success()
        await asyncio.sleep(1.5)
        monitor.record_success()

        assert not failure_event.is_set()
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_monitor_task(self, mock_session):
        """stop() should cancel the monitoring task."""
        monitor = PipelineHealthMonitor(mock_session)
        failure_event = asyncio.Event()

        await monitor.start_monitoring(failure_event)
        assert monitor.is_monitoring

        await monitor.stop()
        assert not monitor.is_monitoring


# ---------------------------------------------------------------------------
# Fallback History Preservation Tests
# ---------------------------------------------------------------------------


class TestTriggerFallback:
    """Tests for _trigger_fallback (conversation history preservation)."""

    @pytest.mark.asyncio
    async def test_preserves_conversation_history(self, mock_session):
        """Should save conversation history to Redis on fallback."""
        with patch("src.realtime.error_recovery.save_conversation_history") as mock_save:
            await _trigger_fallback(mock_session)

        mock_save.assert_called_once_with(
            "CA_test_123",
            list(mock_session.state.conversation_history),
        )

    @pytest.mark.asyncio
    async def test_handles_save_error_gracefully(self, mock_session):
        """Should not crash if saving history fails."""
        with patch(
            "src.realtime.error_recovery.save_conversation_history",
            side_effect=Exception("Redis down"),
        ):
            # Should not raise
            await _trigger_fallback(mock_session)
