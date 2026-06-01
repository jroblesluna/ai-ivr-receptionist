"""Unit tests for src/realtime/models.py."""

import time

from src.realtime.models import (
    OutboundClearMessage,
    OutboundMarkMessage,
    OutboundMediaMessage,
    PipelineState,
    SessionState,
    TwilioConnectedMessage,
    TwilioMediaMessage,
    TwilioStartMessage,
    TwilioStopMessage,
)


class TestPipelineState:
    """Tests for PipelineState enum."""

    def test_has_all_states(self):
        assert PipelineState.LISTENING.value == "listening"
        assert PipelineState.PROCESSING.value == "processing"
        assert PipelineState.SPEAKING.value == "speaking"
        assert PipelineState.INTERRUPTED.value == "interrupted"

    def test_exactly_four_states(self):
        assert len(PipelineState) == 4


class TestSessionState:
    """Tests for SessionState dataclass."""

    def test_required_fields(self):
        s = SessionState(
            call_sid="CA123",
            stream_sid="MZ456",
            language="en",
            demo_id="demo_1",
            caller_from="+14085551234",
            voice_id="voice_abc",
        )
        assert s.call_sid == "CA123"
        assert s.stream_sid == "MZ456"
        assert s.language == "en"
        assert s.demo_id == "demo_1"
        assert s.caller_from == "+14085551234"
        assert s.voice_id == "voice_abc"

    def test_default_values(self):
        before = time.time()
        s = SessionState(
            call_sid="CA1",
            stream_sid="MZ1",
            language="es",
            demo_id="d1",
            caller_from="+1",
            voice_id="v1",
        )
        after = time.time()

        assert s.pipeline_state == PipelineState.LISTENING
        assert s.conversation_history == []
        assert s.collected_info == {}
        assert s.partial_transcript == ""
        assert s.interrupted_text == ""
        assert s.turn_count == 0
        assert before <= s.created_at <= after
        assert before <= s.last_activity_at <= after

    def test_mutable_defaults_are_independent(self):
        s1 = SessionState(
            call_sid="CA1", stream_sid="MZ1", language="en",
            demo_id="d1", caller_from="+1", voice_id="v1",
        )
        s2 = SessionState(
            call_sid="CA2", stream_sid="MZ2", language="en",
            demo_id="d2", caller_from="+2", voice_id="v2",
        )
        s1.conversation_history.append({"role": "user", "content": "hi"})
        s1.collected_info["name"] = "Alice"

        assert s2.conversation_history == []
        assert s2.collected_info == {}


class TestTwilioInboundMessages:
    """Tests for Twilio inbound message TypedDicts."""

    def test_connected_message(self):
        msg: TwilioConnectedMessage = {
            "event": "connected",
            "protocol": "Call",
            "version": "1.0.0",
        }
        assert msg["event"] == "connected"
        assert msg["protocol"] == "Call"

    def test_start_message(self):
        msg: TwilioStartMessage = {
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "streamSid": "MZ123",
                "accountSid": "AC456",
                "callSid": "CA789",
                "customParameters": {
                    "lang": "en",
                    "demo_id": "demo_42",
                    "caller_from": "+14085551234",
                },
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1,
                },
            },
            "streamSid": "MZ123",
        }
        assert msg["start"]["callSid"] == "CA789"
        assert msg["start"]["customParameters"]["lang"] == "en"
        assert msg["start"]["mediaFormat"]["sampleRate"] == 8000

    def test_media_message(self):
        msg: TwilioMediaMessage = {
            "event": "media",
            "sequenceNumber": "4",
            "media": {
                "track": "inbound",
                "chunk": "2",
                "timestamp": "5",
                "payload": "dGVzdA==",
            },
            "streamSid": "MZ123",
        }
        assert msg["media"]["track"] == "inbound"
        assert msg["media"]["payload"] == "dGVzdA=="

    def test_stop_message(self):
        msg: TwilioStopMessage = {
            "event": "stop",
            "sequenceNumber": "100",
            "streamSid": "MZ123",
        }
        assert msg["event"] == "stop"
        assert msg["streamSid"] == "MZ123"


class TestTwilioOutboundMessages:
    """Tests for Twilio outbound message TypedDicts."""

    def test_outbound_media_message(self):
        msg: OutboundMediaMessage = {
            "event": "media",
            "streamSid": "MZ123",
            "media": {"payload": "YXVkaW8="},
        }
        assert msg["event"] == "media"
        assert msg["media"]["payload"] == "YXVkaW8="

    def test_outbound_clear_message(self):
        msg: OutboundClearMessage = {
            "event": "clear",
            "streamSid": "MZ123",
        }
        assert msg["event"] == "clear"
        assert msg["streamSid"] == "MZ123"

    def test_outbound_mark_message(self):
        msg: OutboundMarkMessage = {
            "event": "mark",
            "streamSid": "MZ123",
            "mark": {"name": "chunk_001"},
        }
        assert msg["event"] == "mark"
        assert msg["mark"]["name"] == "chunk_001"
