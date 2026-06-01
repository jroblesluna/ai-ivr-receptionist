"""Latency monitoring and performance logging for the real-time voice pipeline.

Provides the LatencyTracker class that measures time-to-first-audio from
VAD speech_end to first TTS frame sent, logs performance warnings when
total pipeline latency exceeds 2000ms, and provides structured error logging
with call context.

Key measurements:
- Time-to-first-audio: From VAD speech_end to first TTS audio frame sent
- STT finalization time: From speech_end to final transcript received
- LLM first token time: From sending request to first token received
- TTS first audio time: From sending text to first audio chunk received

Requirements: 9.1, 9.2, 9.3, 9.5
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Target time-to-first-audio (ms)
TARGET_TIME_TO_FIRST_AUDIO_MS = 800.0

# Warning threshold for total pipeline latency (ms)
PIPELINE_LATENCY_WARNING_THRESHOLD_MS = 2000.0


# ---------------------------------------------------------------------------
# LatencyTracker
# ---------------------------------------------------------------------------


@dataclass
class LatencyTracker:
    """Tracks latency across the real-time voice pipeline stages.

    Records timestamps at key pipeline stages and calculates the breakdown
    of time spent in each stage. Logs a performance warning when total
    pipeline latency exceeds 2000ms.

    Usage:
        tracker = LatencyTracker(call_sid="CA123")
        tracker.record_speech_end()
        tracker.record_stt_final_transcript()
        tracker.record_llm_request_sent()
        tracker.record_llm_first_token()
        tracker.record_tts_request_sent()
        tracker.record_tts_first_audio()
        tracker.finalize()  # logs breakdown and warns if > 2000ms
    """

    call_sid: str
    stream_sid: str = ""

    # Timestamps (seconds since epoch, set to 0.0 when not yet recorded)
    speech_end_at: float = 0.0
    stt_final_transcript_at: float = 0.0
    llm_request_sent_at: float = 0.0
    llm_first_token_at: float = 0.0
    tts_request_sent_at: float = 0.0
    tts_first_audio_at: float = 0.0

    # Whether this tracker has been finalized
    _finalized: bool = field(default=False, repr=False)

    def reset(self) -> None:
        """Reset all timestamps for a new turn."""
        self.speech_end_at = 0.0
        self.stt_final_transcript_at = 0.0
        self.llm_request_sent_at = 0.0
        self.llm_first_token_at = 0.0
        self.tts_request_sent_at = 0.0
        self.tts_first_audio_at = 0.0
        self._finalized = False

    def record_speech_end(self) -> None:
        """Record the timestamp when VAD detects speech_end."""
        self.speech_end_at = time.time()

    def record_stt_final_transcript(self) -> None:
        """Record the timestamp when STT returns the final transcript."""
        self.stt_final_transcript_at = time.time()

    def record_llm_request_sent(self) -> None:
        """Record the timestamp when the LLM request is sent."""
        self.llm_request_sent_at = time.time()

    def record_llm_first_token(self) -> None:
        """Record the timestamp when the first LLM token is received."""
        self.llm_first_token_at = time.time()

    def record_tts_request_sent(self) -> None:
        """Record the timestamp when text is sent to TTS."""
        self.tts_request_sent_at = time.time()

    def record_tts_first_audio(self) -> None:
        """Record the timestamp when the first TTS audio chunk is received."""
        self.tts_first_audio_at = time.time()

    def get_breakdown(self) -> dict[str, float]:
        """Calculate the latency breakdown in milliseconds.

        Returns a dict with:
        - stt_finalization_ms: Time from speech_end to final transcript
        - llm_first_token_ms: Time from LLM request sent to first token
        - tts_first_audio_ms: Time from TTS request sent to first audio chunk
        - total_ms: Time from speech_end to first TTS audio sent

        Values are 0.0 if the corresponding timestamps haven't been recorded.
        """
        breakdown: dict[str, float] = {
            "stt_finalization_ms": 0.0,
            "llm_first_token_ms": 0.0,
            "tts_first_audio_ms": 0.0,
            "total_ms": 0.0,
        }

        if self.speech_end_at > 0 and self.stt_final_transcript_at > 0:
            breakdown["stt_finalization_ms"] = (
                self.stt_final_transcript_at - self.speech_end_at
            ) * 1000.0

        if self.llm_request_sent_at > 0 and self.llm_first_token_at > 0:
            breakdown["llm_first_token_ms"] = (
                self.llm_first_token_at - self.llm_request_sent_at
            ) * 1000.0

        if self.tts_request_sent_at > 0 and self.tts_first_audio_at > 0:
            breakdown["tts_first_audio_ms"] = (
                self.tts_first_audio_at - self.tts_request_sent_at
            ) * 1000.0

        if self.speech_end_at > 0 and self.tts_first_audio_at > 0:
            breakdown["total_ms"] = (
                self.tts_first_audio_at - self.speech_end_at
            ) * 1000.0

        return breakdown

    def finalize(self) -> dict[str, float]:
        """Finalize the latency measurement and log results.

        Calculates the full breakdown and logs:
        - INFO level: latency breakdown for every turn
        - WARNING level: when total pipeline latency exceeds 2000ms

        Returns:
            The latency breakdown dict.
        """
        if self._finalized:
            return self.get_breakdown()

        self._finalized = True
        breakdown = self.get_breakdown()

        # Always log the latency breakdown at INFO level
        logger.info(
            "Pipeline latency breakdown",
            extra={
                "call_sid": self.call_sid,
                "stream_sid": self.stream_sid,
                "stt_finalization_ms": round(breakdown["stt_finalization_ms"], 1),
                "llm_first_token_ms": round(breakdown["llm_first_token_ms"], 1),
                "tts_first_audio_ms": round(breakdown["tts_first_audio_ms"], 1),
                "total_ms": round(breakdown["total_ms"], 1),
                "target_ms": TARGET_TIME_TO_FIRST_AUDIO_MS,
            },
        )

        # Log WARNING when total exceeds threshold
        if breakdown["total_ms"] > PIPELINE_LATENCY_WARNING_THRESHOLD_MS:
            logger.warning(
                "Pipeline latency exceeds threshold",
                extra={
                    "call_sid": self.call_sid,
                    "stream_sid": self.stream_sid,
                    "total_ms": round(breakdown["total_ms"], 1),
                    "threshold_ms": PIPELINE_LATENCY_WARNING_THRESHOLD_MS,
                    "stt_finalization_ms": round(breakdown["stt_finalization_ms"], 1),
                    "llm_first_token_ms": round(breakdown["llm_first_token_ms"], 1),
                    "tts_first_audio_ms": round(breakdown["tts_first_audio_ms"], 1),
                },
            )

        return breakdown


# ---------------------------------------------------------------------------
# Structured Error Logging
# ---------------------------------------------------------------------------


def log_pipeline_error(
    call_sid: str,
    service: str,
    error_type: str,
    recovery_action: str,
    pipeline_state: str,
    error: Exception | str | None = None,
    stream_sid: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Log a structured error with full pipeline context.

    All error logs across the pipeline include:
    - call_sid: The Twilio call SID
    - service: Service name (deepgram_stt, openai_llm, elevenlabs_tts)
    - error_type: Classification of the error
    - recovery_action: What recovery action was taken
    - pipeline_state: Current state of the pipeline

    Args:
        call_sid: The Twilio call SID for this session.
        service: Service name (e.g., "deepgram_stt", "openai_llm", "elevenlabs_tts").
        error_type: Classification of the error (e.g., "connection_closed", "timeout").
        recovery_action: What recovery action was taken (e.g., "reconnect_attempt_1", "skip_chunk").
        pipeline_state: Current pipeline state value (e.g., "listening", "processing").
        error: The exception or error message string.
        stream_sid: The Twilio stream SID (optional).
        extra: Additional context fields to include in the log.
    """
    log_extra: dict[str, Any] = {
        "call_sid": call_sid,
        "service": service,
        "error_type": error_type,
        "recovery_action": recovery_action,
        "pipeline_state": pipeline_state,
    }

    if stream_sid:
        log_extra["stream_sid"] = stream_sid

    if error is not None:
        log_extra["error"] = str(error)

    if extra:
        log_extra.update(extra)

    logger.error(
        "Pipeline service error: %s",
        error_type,
        extra=log_extra,
    )
