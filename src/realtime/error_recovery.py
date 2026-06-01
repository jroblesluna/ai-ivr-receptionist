"""Error recovery and fallback logic for the real-time voice pipeline.

Implements pipeline-level recovery strategies for STT, LLM, and TTS failures,
plus a full-pipeline health monitor that triggers graceful degradation when
the pipeline is unavailable for >5 seconds.

Recovery strategies:
- STT failure: reconnect within 2s, max 2 attempts, then fallback
- LLM failure: speak apology via TTS, retry once; if retry fails, close stream
- TTS failure: log error, skip current chunk, continue with next (handled in tts.py)
- Full pipeline failure (>5s unavailable): close WebSocket → Twilio triggers fallback

Requirements: 3.5, 3.6, 5.7, 6.6, 10.1, 10.2, 10.4
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from src.realtime.store_integration import save_conversation_history

if TYPE_CHECKING:
    from fastapi import WebSocket

    from src.realtime.session import ConversationSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum time (seconds) the pipeline can be unavailable before triggering fallback
PIPELINE_UNAVAILABLE_TIMEOUT_S = 5.0

# Apology messages by language
APOLOGY_MESSAGES = {
    "en": "I'm sorry, I'm having a brief technical issue. One moment please.",
    "es": "Lo siento, estoy teniendo un problema técnico. Un momento por favor.",
}

# Default language for apology if session language not found
_DEFAULT_APOLOGY_LANG = "en"


# ---------------------------------------------------------------------------
# STT Failure Recovery
# ---------------------------------------------------------------------------


async def handle_stt_failure(
    session: "ConversationSession",
    ws: "WebSocket",
) -> bool:
    """Handle STT connection failure with reconnection attempts.

    Attempts to reconnect the STT client (already supports 2 attempts with
    2s timeout each via DeepgramSTTClient.reconnect()). If reconnection fails,
    preserves conversation history in Redis and signals that the WebSocket
    should be closed (Twilio will trigger fallback to <Gather speech>).

    Args:
        session: The active ConversationSession.
        ws: The WebSocket connection.

    Returns:
        True if recovery succeeded (STT reconnected), False if fallback needed.
    """
    logger.warning(
        "STT failure detected, attempting recovery",
        extra={
            "call_sid": session.call_sid,
            "stream_sid": session.stream_sid,
            "service": "deepgram_stt",
            "error_type": "connection_lost",
            "recovery_action": "reconnect",
            "pipeline_state": session.pipeline_state.value,
        },
    )

    if session.stt_client is None:
        logger.error(
            "STT client is None, cannot recover",
            extra={"call_sid": session.call_sid, "stream_sid": session.stream_sid},
        )
        await _trigger_fallback(session)
        return False

    # Attempt reconnection (DeepgramSTTClient.reconnect handles 2 attempts, 2s each)
    reconnected = await session.stt_client.reconnect()

    if reconnected:
        logger.info(
            "STT recovery successful",
            extra={
                "call_sid": session.call_sid,
                "stream_sid": session.stream_sid,
                "service": "deepgram_stt",
                "recovery_action": "reconnect_success",
            },
        )
        return True

    # Reconnection failed — trigger fallback
    logger.error(
        "STT recovery failed after max attempts, triggering fallback",
        extra={
            "call_sid": session.call_sid,
            "stream_sid": session.stream_sid,
            "service": "deepgram_stt",
            "error_type": "reconnect_exhausted",
            "recovery_action": "fallback_to_gather",
            "pipeline_state": session.pipeline_state.value,
        },
    )
    await _trigger_fallback(session)
    return False


# ---------------------------------------------------------------------------
# LLM Failure Recovery
# ---------------------------------------------------------------------------


async def handle_llm_failure(
    session: "ConversationSession",
    ws: "WebSocket",
    messages: list[dict],
    on_sentence_chunk,
    on_complete,
    cancel_event: asyncio.Event,
) -> bool:
    """Handle LLM generation failure with apology + single retry.

    On LLM failure:
    1. Speak an apology message via TTS to the caller
    2. Retry the LLM request once
    3. If retry also fails, close the stream (triggering fallback)

    Args:
        session: The active ConversationSession.
        ws: The WebSocket connection.
        messages: The conversation messages to retry with.
        on_sentence_chunk: Callback for sentence chunks (for retry).
        on_complete: Callback for completion (for retry).
        cancel_event: Cancellation event for barge-in.

    Returns:
        True if retry succeeded, False if fallback needed.
    """
    logger.warning(
        "LLM failure detected, speaking apology and retrying",
        extra={
            "call_sid": session.call_sid,
            "stream_sid": session.stream_sid,
            "service": "openai_llm",
            "error_type": "generation_failed",
            "recovery_action": "apology_and_retry",
            "pipeline_state": session.pipeline_state.value,
        },
    )

    # Step 1: Speak apology via TTS
    await _speak_apology(session, ws)

    # Step 2: Retry LLM generation once
    if cancel_event.is_set():
        # Barge-in happened during apology — don't retry
        return False

    try:
        from src.realtime.llm import LLMStreamClient

        retry_client = LLMStreamClient()
        await retry_client.generate_response(
            messages=messages,
            on_sentence_chunk=on_sentence_chunk,
            on_complete=on_complete,
            cancel_event=cancel_event,
        )
        logger.info(
            "LLM retry successful",
            extra={
                "call_sid": session.call_sid,
                "stream_sid": session.stream_sid,
                "service": "openai_llm",
                "recovery_action": "retry_success",
            },
        )
        return True

    except Exception as retry_exc:
        logger.error(
            "LLM retry also failed, triggering fallback",
            extra={
                "call_sid": session.call_sid,
                "stream_sid": session.stream_sid,
                "service": "openai_llm",
                "error_type": "retry_failed",
                "error": str(retry_exc),
                "recovery_action": "close_stream",
                "pipeline_state": session.pipeline_state.value,
            },
        )
        await _trigger_fallback(session)
        return False


# ---------------------------------------------------------------------------
# Full Pipeline Health Monitor
# ---------------------------------------------------------------------------


class PipelineHealthMonitor:
    """Monitors pipeline health and triggers fallback if unavailable >5s.

    Tracks the last successful processing timestamp. If no successful
    processing occurs within PIPELINE_UNAVAILABLE_TIMEOUT_S (5 seconds),
    the monitor signals that the WebSocket should be closed.
    """

    def __init__(self, session: "ConversationSession") -> None:
        self._session = session
        self._last_success_time: float = time.monotonic()
        self._monitoring: bool = False
        self._monitor_task: asyncio.Task | None = None

    @property
    def is_monitoring(self) -> bool:
        """Whether the monitor is currently active."""
        return self._monitoring

    def record_success(self) -> None:
        """Record a successful pipeline processing event.

        Call this whenever audio is successfully processed through any
        part of the pipeline (STT transcript received, TTS audio sent, etc.)
        """
        self._last_success_time = time.monotonic()

    def time_since_last_success(self) -> float:
        """Return seconds elapsed since last successful processing."""
        return time.monotonic() - self._last_success_time

    def is_pipeline_unavailable(self) -> bool:
        """Check if the pipeline has been unavailable for >5 seconds."""
        return self.time_since_last_success() > PIPELINE_UNAVAILABLE_TIMEOUT_S

    async def start_monitoring(self, on_failure: asyncio.Event) -> None:
        """Start background monitoring of pipeline health.

        Sets the on_failure event if the pipeline is unavailable for >5s.

        Args:
            on_failure: Event to set when pipeline failure is detected.
        """
        self._monitoring = True
        self._last_success_time = time.monotonic()
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(on_failure)
        )

    async def _monitor_loop(self, on_failure: asyncio.Event) -> None:
        """Background loop that checks pipeline health every second."""
        try:
            while self._monitoring:
                await asyncio.sleep(1.0)
                if self.is_pipeline_unavailable():
                    logger.error(
                        "Full pipeline failure detected (>5s unavailable)",
                        extra={
                            "call_sid": self._session.call_sid,
                            "stream_sid": self._session.stream_sid,
                            "seconds_since_success": self.time_since_last_success(),
                            "recovery_action": "close_websocket",
                            "pipeline_state": self._session.pipeline_state.value,
                        },
                    )
                    # Preserve conversation history before closing
                    await _trigger_fallback(self._session)
                    on_failure.set()
                    break
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """Stop the health monitor."""
        self._monitoring = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except (asyncio.CancelledError, Exception):
                pass
            self._monitor_task = None


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------


async def _speak_apology(
    session: "ConversationSession",
    ws: "WebSocket",
) -> None:
    """Synthesize and send an apology message to the caller via TTS.

    Uses the session's language to select the appropriate apology message.

    Args:
        session: The active ConversationSession.
        ws: The WebSocket connection for sending audio.
    """
    lang = session.language if session.language in APOLOGY_MESSAGES else _DEFAULT_APOLOGY_LANG
    apology_text = APOLOGY_MESSAGES[lang]

    if session.tts_client is None:
        logger.warning(
            "Cannot speak apology — TTS client unavailable",
            extra={"call_sid": session.call_sid, "stream_sid": session.stream_sid},
        )
        return

    from src.realtime.models import encode_audio_for_twilio

    async def send_audio_chunk(audio_chunk: bytes) -> None:
        """Send a TTS audio chunk to Twilio."""
        try:
            media_message = encode_audio_for_twilio(audio_chunk, session.stream_sid)
            await ws.send_json(media_message)
        except Exception as exc:
            logger.warning(
                "Error sending apology audio to Twilio",
                extra={
                    "stream_sid": session.stream_sid,
                    "error": str(exc),
                },
            )

    try:
        await session.tts_client.synthesize_stream(
            text=apology_text,
            voice_id=session.voice_id or session.state.voice_id,
            on_audio_chunk=send_audio_chunk,
        )
        logger.info(
            "Apology message spoken",
            extra={
                "call_sid": session.call_sid,
                "stream_sid": session.stream_sid,
                "language": lang,
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to speak apology message",
            extra={
                "call_sid": session.call_sid,
                "stream_sid": session.stream_sid,
                "error": str(exc),
            },
        )


async def _trigger_fallback(session: "ConversationSession") -> None:
    """Preserve conversation history in Redis before fallback.

    Saves the current conversation history so the <Gather speech> fallback
    flow can continue the conversation where it left off.

    Args:
        session: The active ConversationSession.
    """
    try:
        save_conversation_history(
            session.call_sid,
            list(session.state.conversation_history),
        )
        logger.info(
            "Conversation history preserved for fallback",
            extra={
                "call_sid": session.call_sid,
                "stream_sid": session.stream_sid,
                "message_count": len(session.state.conversation_history),
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to preserve conversation history for fallback",
            extra={
                "call_sid": session.call_sid,
                "stream_sid": session.stream_sid,
                "error": str(exc),
            },
        )
