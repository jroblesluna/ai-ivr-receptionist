"""Unit tests for src/realtime/latency.py — latency monitoring and performance logging."""

import logging
import time
from unittest.mock import patch

import pytest

from src.realtime.latency import (
    PIPELINE_LATENCY_WARNING_THRESHOLD_MS,
    TARGET_TIME_TO_FIRST_AUDIO_MS,
    LatencyTracker,
    log_pipeline_error,
)


class TestLatencyTracker:
    """Tests for LatencyTracker class."""

    def test_initial_state(self):
        tracker = LatencyTracker(call_sid="CA123", stream_sid="MZ456")
        assert tracker.call_sid == "CA123"
        assert tracker.stream_sid == "MZ456"
        assert tracker.speech_end_at == 0.0
        assert tracker.stt_final_transcript_at == 0.0
        assert tracker.llm_request_sent_at == 0.0
        assert tracker.llm_first_token_at == 0.0
        assert tracker.tts_request_sent_at == 0.0
        assert tracker.tts_first_audio_at == 0.0

    def test_record_speech_end(self):
        tracker = LatencyTracker(call_sid="CA123")
        before = time.time()
        tracker.record_speech_end()
        after = time.time()
        assert before <= tracker.speech_end_at <= after

    def test_record_stt_final_transcript(self):
        tracker = LatencyTracker(call_sid="CA123")
        before = time.time()
        tracker.record_stt_final_transcript()
        after = time.time()
        assert before <= tracker.stt_final_transcript_at <= after

    def test_record_llm_request_sent(self):
        tracker = LatencyTracker(call_sid="CA123")
        before = time.time()
        tracker.record_llm_request_sent()
        after = time.time()
        assert before <= tracker.llm_request_sent_at <= after

    def test_record_llm_first_token(self):
        tracker = LatencyTracker(call_sid="CA123")
        before = time.time()
        tracker.record_llm_first_token()
        after = time.time()
        assert before <= tracker.llm_first_token_at <= after

    def test_record_tts_request_sent(self):
        tracker = LatencyTracker(call_sid="CA123")
        before = time.time()
        tracker.record_tts_request_sent()
        after = time.time()
        assert before <= tracker.tts_request_sent_at <= after

    def test_record_tts_first_audio(self):
        tracker = LatencyTracker(call_sid="CA123")
        before = time.time()
        tracker.record_tts_first_audio()
        after = time.time()
        assert before <= tracker.tts_first_audio_at <= after

    def test_reset_clears_all_timestamps(self):
        tracker = LatencyTracker(call_sid="CA123")
        tracker.record_speech_end()
        tracker.record_stt_final_transcript()
        tracker.record_llm_request_sent()
        tracker.record_llm_first_token()
        tracker.record_tts_request_sent()
        tracker.record_tts_first_audio()

        tracker.reset()

        assert tracker.speech_end_at == 0.0
        assert tracker.stt_final_transcript_at == 0.0
        assert tracker.llm_request_sent_at == 0.0
        assert tracker.llm_first_token_at == 0.0
        assert tracker.tts_request_sent_at == 0.0
        assert tracker.tts_first_audio_at == 0.0
        assert tracker._finalized is False

    def test_get_breakdown_all_zeros_when_no_timestamps(self):
        tracker = LatencyTracker(call_sid="CA123")
        breakdown = tracker.get_breakdown()
        assert breakdown["stt_finalization_ms"] == 0.0
        assert breakdown["llm_first_token_ms"] == 0.0
        assert breakdown["tts_first_audio_ms"] == 0.0
        assert breakdown["total_ms"] == 0.0

    def test_get_breakdown_calculates_stt_finalization(self):
        tracker = LatencyTracker(call_sid="CA123")
        tracker.speech_end_at = 1000.0
        tracker.stt_final_transcript_at = 1000.150  # 150ms later
        breakdown = tracker.get_breakdown()
        assert abs(breakdown["stt_finalization_ms"] - 150.0) < 0.01

    def test_get_breakdown_calculates_llm_first_token(self):
        tracker = LatencyTracker(call_sid="CA123")
        tracker.llm_request_sent_at = 1000.0
        tracker.llm_first_token_at = 1000.300  # 300ms later
        breakdown = tracker.get_breakdown()
        assert abs(breakdown["llm_first_token_ms"] - 300.0) < 0.01

    def test_get_breakdown_calculates_tts_first_audio(self):
        tracker = LatencyTracker(call_sid="CA123")
        tracker.tts_request_sent_at = 1000.0
        tracker.tts_first_audio_at = 1000.200  # 200ms later
        breakdown = tracker.get_breakdown()
        assert abs(breakdown["tts_first_audio_ms"] - 200.0) < 0.01

    def test_get_breakdown_calculates_total(self):
        tracker = LatencyTracker(call_sid="CA123")
        tracker.speech_end_at = 1000.0
        tracker.tts_first_audio_at = 1000.750  # 750ms total
        breakdown = tracker.get_breakdown()
        assert abs(breakdown["total_ms"] - 750.0) < 0.01

    def test_get_breakdown_full_pipeline(self):
        """Test a realistic full pipeline breakdown."""
        tracker = LatencyTracker(call_sid="CA123")
        tracker.speech_end_at = 1000.0
        tracker.stt_final_transcript_at = 1000.100  # 100ms STT
        tracker.llm_request_sent_at = 1000.105
        tracker.llm_first_token_at = 1000.400  # 295ms LLM
        tracker.tts_request_sent_at = 1000.410
        tracker.tts_first_audio_at = 1000.600  # 190ms TTS

        breakdown = tracker.get_breakdown()
        assert abs(breakdown["stt_finalization_ms"] - 100.0) < 0.01
        assert abs(breakdown["llm_first_token_ms"] - 295.0) < 0.01
        assert abs(breakdown["tts_first_audio_ms"] - 190.0) < 0.01
        assert abs(breakdown["total_ms"] - 600.0) < 0.01

    def test_finalize_logs_info(self, caplog):
        """Test that finalize logs at INFO level."""
        tracker = LatencyTracker(call_sid="CA123", stream_sid="MZ456")
        tracker.speech_end_at = 1000.0
        tracker.stt_final_transcript_at = 1000.100
        tracker.llm_request_sent_at = 1000.105
        tracker.llm_first_token_at = 1000.300
        tracker.tts_request_sent_at = 1000.310
        tracker.tts_first_audio_at = 1000.500

        with caplog.at_level(logging.INFO, logger="src.realtime.latency"):
            breakdown = tracker.finalize()

        assert breakdown["total_ms"] == pytest.approx(500.0, abs=0.01)
        assert "Pipeline latency breakdown" in caplog.text

    def test_finalize_logs_warning_when_exceeds_threshold(self, caplog):
        """Test that finalize logs WARNING when total > 2000ms."""
        tracker = LatencyTracker(call_sid="CA123", stream_sid="MZ456")
        tracker.speech_end_at = 1000.0
        tracker.stt_final_transcript_at = 1000.500
        tracker.llm_request_sent_at = 1000.510
        tracker.llm_first_token_at = 1001.500
        tracker.tts_request_sent_at = 1001.510
        tracker.tts_first_audio_at = 1002.500  # 2500ms total

        with caplog.at_level(logging.WARNING, logger="src.realtime.latency"):
            breakdown = tracker.finalize()

        assert breakdown["total_ms"] == pytest.approx(2500.0, abs=0.01)
        assert "Pipeline latency exceeds threshold" in caplog.text

    def test_finalize_no_warning_when_under_threshold(self, caplog):
        """Test that finalize does NOT log WARNING when total < 2000ms."""
        tracker = LatencyTracker(call_sid="CA123", stream_sid="MZ456")
        tracker.speech_end_at = 1000.0
        tracker.tts_first_audio_at = 1000.500  # 500ms total

        with caplog.at_level(logging.WARNING, logger="src.realtime.latency"):
            tracker.finalize()

        assert "Pipeline latency exceeds threshold" not in caplog.text

    def test_finalize_idempotent(self):
        """Test that calling finalize multiple times returns same result."""
        tracker = LatencyTracker(call_sid="CA123")
        tracker.speech_end_at = 1000.0
        tracker.tts_first_audio_at = 1000.700

        breakdown1 = tracker.finalize()
        breakdown2 = tracker.finalize()
        assert breakdown1 == breakdown2

    def test_partial_timestamps_only_compute_available(self):
        """Test that missing timestamps result in 0.0 for those stages."""
        tracker = LatencyTracker(call_sid="CA123")
        # Only speech_end and stt_final set
        tracker.speech_end_at = 1000.0
        tracker.stt_final_transcript_at = 1000.200

        breakdown = tracker.get_breakdown()
        assert abs(breakdown["stt_finalization_ms"] - 200.0) < 0.01
        assert breakdown["llm_first_token_ms"] == 0.0
        assert breakdown["tts_first_audio_ms"] == 0.0
        assert breakdown["total_ms"] == 0.0  # No tts_first_audio_at


class TestLogPipelineError:
    """Tests for log_pipeline_error structured error logging."""

    def test_logs_error_with_all_required_fields(self, caplog):
        """Test that all required structured fields are present in the log."""
        with caplog.at_level(logging.ERROR, logger="src.realtime.latency"):
            log_pipeline_error(
                call_sid="CA123",
                service="deepgram_stt",
                error_type="connection_closed",
                recovery_action="reconnect_attempt_1",
                pipeline_state="listening",
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.call_sid == "CA123"
        assert record.service == "deepgram_stt"
        assert record.error_type == "connection_closed"
        assert record.recovery_action == "reconnect_attempt_1"
        assert record.pipeline_state == "listening"

    def test_logs_error_with_stream_sid(self, caplog):
        """Test that stream_sid is included when provided."""
        with caplog.at_level(logging.ERROR, logger="src.realtime.latency"):
            log_pipeline_error(
                call_sid="CA123",
                service="openai_llm",
                error_type="timeout",
                recovery_action="retry_once",
                pipeline_state="processing",
                stream_sid="MZ456",
            )

        record = caplog.records[0]
        assert record.stream_sid == "MZ456"

    def test_logs_error_with_exception(self, caplog):
        """Test that error field is included when an exception is provided."""
        exc = ConnectionError("Connection refused")
        with caplog.at_level(logging.ERROR, logger="src.realtime.latency"):
            log_pipeline_error(
                call_sid="CA123",
                service="elevenlabs_tts",
                error_type="connection_error",
                recovery_action="skip_chunk",
                pipeline_state="speaking",
                error=exc,
            )

        record = caplog.records[0]
        assert record.error == "Connection refused"

    def test_logs_error_with_string_error(self, caplog):
        """Test that error field works with a plain string."""
        with caplog.at_level(logging.ERROR, logger="src.realtime.latency"):
            log_pipeline_error(
                call_sid="CA123",
                service="deepgram_stt",
                error_type="decode_error",
                recovery_action="skip_frame",
                pipeline_state="listening",
                error="Invalid audio frame",
            )

        record = caplog.records[0]
        assert record.error == "Invalid audio frame"

    def test_logs_error_with_extra_fields(self, caplog):
        """Test that additional extra fields are included."""
        with caplog.at_level(logging.ERROR, logger="src.realtime.latency"):
            log_pipeline_error(
                call_sid="CA123",
                service="openai_llm",
                error_type="rate_limit",
                recovery_action="backoff_retry",
                pipeline_state="processing",
                extra={"retry_count": 2, "wait_seconds": 5},
            )

        record = caplog.records[0]
        assert record.retry_count == 2
        assert record.wait_seconds == 5

    def test_logs_at_error_level(self, caplog):
        """Test that log_pipeline_error logs at ERROR level."""
        with caplog.at_level(logging.ERROR, logger="src.realtime.latency"):
            log_pipeline_error(
                call_sid="CA123",
                service="deepgram_stt",
                error_type="connection_closed",
                recovery_action="reconnect_attempt_1",
                pipeline_state="listening",
            )

        assert caplog.records[0].levelno == logging.ERROR

    def test_all_service_names(self, caplog):
        """Test that all expected service names work correctly."""
        services = ["deepgram_stt", "openai_llm", "elevenlabs_tts"]
        for service in services:
            caplog.clear()
            with caplog.at_level(logging.ERROR, logger="src.realtime.latency"):
                log_pipeline_error(
                    call_sid="CA123",
                    service=service,
                    error_type="test_error",
                    recovery_action="test_action",
                    pipeline_state="listening",
                )
            assert caplog.records[0].service == service
