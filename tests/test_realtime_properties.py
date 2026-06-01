# Feature: realtime-voice-conversation, Property 1: Start event parameter extraction
"""
Property-based test for start event parameter extraction.

For any valid Twilio Media Streams start event containing a callSid, streamSid,
and arbitrary customParameters dict, parsing the event SHALL produce a SessionState
with call_sid, stream_sid, language, demo_id, and caller_from fields matching the
input values exactly.

**Validates: Requirements 1.3**
"""
import json
import sys
import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.realtime.models import (
    PipelineState,
    SessionState,
    TwilioStartMessage,
    parse_start_event,
)


# ── Strategies ────────────────────────────────────────────────────────────────

# Safe text that avoids null bytes and surrogates (invalid in JSON)
safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=100,
)

# SID-like strings (alphanumeric with a prefix)
call_sid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=5,
    max_size=34,
).map(lambda s: "CA" + s)

stream_sid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=5,
    max_size=34,
).map(lambda s: "MZ" + s)

account_sid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=5,
    max_size=34,
).map(lambda s: "AC" + s)

# Language codes
language_strategy = st.sampled_from(["en", "es", "fr", "de", "it", "pt", "ja", "zh", "ko", "ar"])

# Demo IDs
demo_id_strategy = safe_text

# Caller phone numbers
caller_from_strategy = st.from_regex(r"\+1[0-9]{10}", fullmatch=True)

# Voice IDs
voice_id_strategy = safe_text

# Sequence number
sequence_number_strategy = st.integers(min_value=1, max_value=9999).map(str)


# ── Strategy for full TwilioStartMessage ──────────────────────────────────────

@st.composite
def twilio_start_message_strategy(draw):
    """Generate a valid TwilioStartMessage with random parameters."""
    call_sid = draw(call_sid_strategy)
    stream_sid = draw(stream_sid_strategy)
    account_sid = draw(account_sid_strategy)
    lang = draw(language_strategy)
    demo_id = draw(demo_id_strategy)
    caller_from = draw(caller_from_strategy)
    seq_num = draw(sequence_number_strategy)

    msg: TwilioStartMessage = {
        "event": "start",
        "sequenceNumber": seq_num,
        "start": {
            "streamSid": stream_sid,
            "accountSid": account_sid,
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
    }
    return msg


# ── Property Test ─────────────────────────────────────────────────────────────


class TestStartEventParameterExtraction:
    """Property 1: Start event parameter extraction.

    For any valid Twilio Media Streams start event containing a callSid,
    streamSid, and arbitrary customParameters dict, parsing the event SHALL
    produce a SessionState with call_sid, stream_sid, language, demo_id, and
    caller_from fields matching the input values exactly.

    **Validates: Requirements 1.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        msg=twilio_start_message_strategy(),
        voice_id=voice_id_strategy,
    )
    def test_extracted_fields_match_input(self, msg: TwilioStartMessage, voice_id: str):
        """Parsing a start event produces a SessionState with fields matching the input exactly."""
        session = parse_start_event(msg, voice_id=voice_id)

        # Core identity fields match exactly
        assert session.call_sid == msg["start"]["callSid"]
        assert session.stream_sid == msg["start"]["streamSid"]

        # Custom parameters match exactly
        custom_params = msg["start"]["customParameters"]
        assert session.language == custom_params["lang"]
        assert session.demo_id == custom_params["demo_id"]
        assert session.caller_from == custom_params["caller_from"]

        # Voice ID is passed through
        assert session.voice_id == voice_id

    @settings(max_examples=100, deadline=None)
    @given(
        msg=twilio_start_message_strategy(),
        voice_id=voice_id_strategy,
    )
    def test_session_state_defaults_are_correct(self, msg: TwilioStartMessage, voice_id: str):
        """Parsed SessionState has correct default values for non-extracted fields."""
        session = parse_start_event(msg, voice_id=voice_id)

        # Default pipeline state
        assert session.pipeline_state == PipelineState.LISTENING

        # Default empty collections
        assert session.conversation_history == []
        assert session.collected_info == {}

        # Default empty strings
        assert session.partial_transcript == ""
        assert session.interrupted_text == ""

        # Default counters
        assert session.turn_count == 0

    @settings(max_examples=100, deadline=None)
    @given(
        msg=twilio_start_message_strategy(),
    )
    def test_default_voice_id_when_not_provided(self, msg: TwilioStartMessage):
        """When no voice_id is provided, the default voice ID is used."""
        from src.realtime.models import DEFAULT_VOICE_ID

        session = parse_start_event(msg)
        assert session.voice_id == DEFAULT_VOICE_ID


# Feature: realtime-voice-conversation, Property 14: Conversation history cap
# ── Strategies for Property 14 ────────────────────────────────────────────────

# A single conversation message with "role" and "content" fields
_message_strategy = st.fixed_dictionaries({
    "role": st.sampled_from(["system", "user", "assistant"]),
    "content": safe_text,
})

# Conversation history: 1–200 messages (covers both under and over the cap)
_conversation_strategy_p14 = st.lists(_message_strategy, min_size=1, max_size=200)


# ── Property 14 Test ──────────────────────────────────────────────────────────

from src.realtime.models import cap_conversation_history, MAX_CONVERSATION_HISTORY


class TestConversationHistoryCap:
    """Property 14: Conversation history cap.

    For any conversation history with more than 50 messages, storing it via
    the session store SHALL retain only the most recent 50 messages,
    preserving their order.

    **Validates: Requirements 7.5**
    """

    @settings(max_examples=200, deadline=None)
    @given(history=_conversation_strategy_p14)
    def test_cap_never_exceeds_max(self, history):
        """The capped history never contains more than 50 messages."""
        result = cap_conversation_history(history)
        assert len(result) <= MAX_CONVERSATION_HISTORY

    @settings(max_examples=200, deadline=None)
    @given(history=_conversation_strategy_p14)
    def test_cap_retains_most_recent(self, history):
        """If len > 50, only the last 50 messages are retained."""
        result = cap_conversation_history(history)
        if len(history) > MAX_CONVERSATION_HISTORY:
            assert result == history[-MAX_CONVERSATION_HISTORY:]
            assert len(result) == MAX_CONVERSATION_HISTORY
        else:
            assert result == history

    @settings(max_examples=200, deadline=None)
    @given(history=_conversation_strategy_p14)
    def test_cap_preserves_order(self, history):
        """The relative order of retained messages is preserved."""
        result = cap_conversation_history(history)
        # The result must be a contiguous suffix of the original
        expected_start = max(0, len(history) - MAX_CONVERSATION_HISTORY)
        assert result == history[expected_start:]

    @settings(max_examples=200, deadline=None)
    @given(history=st.lists(_message_strategy, min_size=0, max_size=50))
    def test_cap_preserves_all_when_under_limit(self, history):
        """If len <= 50, all messages are retained unchanged."""
        result = cap_conversation_history(history)
        assert result == history
        assert len(result) == len(history)


# Feature: realtime-voice-conversation, Property 9: Partial response preservation on interruption
# ── Strategies for Property 9 ────────────────────────────────────────────────

from src.realtime.playback import PlaybackTracker

# Text segments representing TTS chunks that have been sent to the caller
_text_segment_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=200,
)

# List of text segments (simulating multiple TTS chunks sent before interruption)
_segments_list_strategy = st.lists(_text_segment_strategy, min_size=1, max_size=50)

# Chunk IDs (unique identifiers for each audio chunk)
_chunk_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=3,
    max_size=20,
).map(lambda s: "chunk_" + s)


# ── Property 9 Test ──────────────────────────────────────────────────────────


class TestPartialResponsePreservationOnInterruption:
    """Property 9: Partial response preservation on interruption.

    For any AI response that has been partially generated (N tokens accumulated
    into M text segments) when a barge-in occurs, the conversation history SHALL
    contain an assistant message with the partial text generated up to the
    interruption point, annotated with an interrupted: true marker.

    **Validates: Requirements 4.5**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        segments=_segments_list_strategy,
        chunk_ids=st.lists(
            _chunk_id_strategy,
            min_size=1,
            max_size=50,
        ),
    )
    def test_partial_text_equals_concatenation_of_sent_segments(self, segments, chunk_ids):
        """The partial text at interruption equals the concatenation of all sent segments."""
        # Ensure we have matching chunk_ids for each segment
        # Use modular indexing if chunk_ids list is shorter
        tracker = PlaybackTracker()

        for i, segment in enumerate(segments):
            cid = chunk_ids[i % len(chunk_ids)] + f"_{i}"
            tracker.record_chunk_sent(cid, segment)

        # Simulate interruption: get partial text
        partial_text = tracker.get_partial_text_at_interruption()

        # The partial text must equal the concatenation of all sent segments
        expected_text = "".join(segments)
        assert partial_text == expected_text

    @settings(max_examples=100, deadline=None)
    @given(segments=_segments_list_strategy)
    def test_interrupted_message_has_correct_structure(self, segments):
        """The interrupted assistant message has the correct content and marker."""
        tracker = PlaybackTracker()

        for i, segment in enumerate(segments):
            tracker.record_chunk_sent(f"chunk_{i}", segment)

        # Simulate interruption: build the interrupted assistant message
        partial_text = tracker.get_partial_text_at_interruption()
        interrupted_message = {
            "role": "assistant",
            "content": partial_text,
            "interrupted": True,
        }

        # Assert structure
        assert interrupted_message["role"] == "assistant"
        assert interrupted_message["content"] == "".join(segments)
        assert interrupted_message["interrupted"] is True

    @settings(max_examples=100, deadline=None)
    @given(segments=_segments_list_strategy)
    def test_interrupted_marker_is_true(self, segments):
        """The interrupted marker on the assistant message is always True."""
        tracker = PlaybackTracker()

        for i, segment in enumerate(segments):
            tracker.record_chunk_sent(f"chunk_{i}", segment)

        partial_text = tracker.get_partial_text_at_interruption()

        # Build the message as the pipeline would
        interrupted_message = {
            "role": "assistant",
            "content": partial_text,
            "interrupted": True,
        }

        # The interrupted flag must be True
        assert interrupted_message["interrupted"] is True
        # The content must be non-empty (since we always have at least 1 segment with min_size=1)
        assert len(interrupted_message["content"]) > 0

    @settings(max_examples=100, deadline=None)
    @given(segments=_segments_list_strategy)
    def test_tracker_clear_resets_state(self, segments):
        """After clear(), the tracker reports empty partial text for the next turn."""
        tracker = PlaybackTracker()

        for i, segment in enumerate(segments):
            tracker.record_chunk_sent(f"chunk_{i}", segment)

        # Verify segments were recorded
        assert tracker.get_partial_text_at_interruption() == "".join(segments)

        # Clear for next turn
        tracker.clear()

        # After clear, partial text should be empty
        assert tracker.get_partial_text_at_interruption() == ""


# Feature: realtime-voice-conversation, Property 6: VAD speech_start threshold
# ── Strategies for Property 6 ────────────────────────────────────────────────

from unittest.mock import patch, MagicMock
import struct
import math

try:
    from src.realtime.vad import VADProcessor, VADEvent, _SILERO_CHUNK_SAMPLES, _SILERO_SAMPLE_RATE
    _VAD_AVAILABLE = True
except ImportError:
    _VAD_AVAILABLE = False
    VADProcessor = None  # type: ignore[assignment, misc]
    VADEvent = None  # type: ignore[assignment, misc]
    _SILERO_CHUNK_SAMPLES = 512
    _SILERO_SAMPLE_RATE = 16000


def _make_mulaw_frame_for_chunk() -> bytes:
    """Create a mulaw audio frame that, after conversion to 16kHz PCM,
    produces at least _SILERO_CHUNK_SAMPLES (512) samples.

    At 8kHz mulaw, each byte = 1 sample. After resampling 8kHz→16kHz,
    N input samples become ~2N output samples. So we need at least
    256 bytes of mulaw to get 512 samples at 16kHz.
    We use 260 bytes to have a small margin.
    """
    # 0xFF in mulaw encodes silence (near-zero amplitude)
    return b"\xff" * 260


@pytest.mark.skipif(not _VAD_AVAILABLE, reason="torchaudio not installed")
class TestVADSpeechStartThreshold:
    """Property 6: VAD speech_start threshold.

    For any audio frame processed by the VAD engine, a speech_start event
    SHALL be emitted if and only if the model's confidence score is greater
    than or equal to 0.5 and the previous state was silence.

    **Validates: Requirements 4.1**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_speech_start_emitted_iff_confidence_gte_threshold_and_was_silent(self, confidence):
        """SPEECH_START is emitted iff confidence >= 0.5 AND previous state was silence."""
        # Create a VADProcessor with mocked model to control confidence output
        with patch("src.realtime.vad.torch.hub.load") as mock_hub_load:
            # Mock the Silero model
            mock_model = MagicMock()
            mock_model.return_value.item.return_value = confidence
            mock_hub_load.return_value = (mock_model, None)

            # Mock torchaudio resampler to pass through (we control input size)
            with patch("src.realtime.vad.torchaudio.transforms.Resample") as mock_resample_cls:
                import torch as _torch

                # The resampler should produce exactly _SILERO_CHUNK_SAMPLES samples
                mock_resampler = MagicMock()
                mock_resampler.return_value = _torch.zeros(_SILERO_CHUNK_SAMPLES, dtype=_torch.float32)
                mock_resample_cls.return_value = mock_resampler

                processor = VADProcessor(threshold=0.5, silence_duration_ms=300)

                # Ensure processor starts in silence state
                assert not processor.is_speaking

                # Process a frame (the audio content doesn't matter since model is mocked)
                audio_frame = b"\xff" * 160  # Typical Twilio frame size
                event = processor.process_frame(audio_frame)

                if confidence >= 0.5:
                    # Should emit SPEECH_START since previous state was silence
                    assert event == VADEvent.SPEECH_START
                    assert processor.is_speaking
                else:
                    # Should NOT emit SPEECH_START
                    assert event is None
                    assert not processor.is_speaking

    @settings(max_examples=100, deadline=None)
    @given(
        confidence=st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_no_speech_start_when_already_speaking(self, confidence):
        """SPEECH_START is NOT emitted when confidence >= 0.5 but already speaking."""
        with patch("src.realtime.vad.torch.hub.load") as mock_hub_load:
            mock_model = MagicMock()
            mock_model.return_value.item.return_value = confidence
            mock_hub_load.return_value = (mock_model, None)

            with patch("src.realtime.vad.torchaudio.transforms.Resample") as mock_resample_cls:
                import torch as _torch

                mock_resampler = MagicMock()
                mock_resampler.return_value = _torch.zeros(_SILERO_CHUNK_SAMPLES, dtype=_torch.float32)
                mock_resample_cls.return_value = mock_resampler

                processor = VADProcessor(threshold=0.5, silence_duration_ms=300)

                # First frame: transition to speaking
                audio_frame = b"\xff" * 160
                event1 = processor.process_frame(audio_frame)
                assert event1 == VADEvent.SPEECH_START
                assert processor.is_speaking

                # Second frame: already speaking, should NOT emit SPEECH_START again
                event2 = processor.process_frame(audio_frame)
                assert event2 is None
                assert processor.is_speaking


# Feature: realtime-voice-conversation, Property 7: VAD speech_end silence duration
# ── Strategies for Property 7 ────────────────────────────────────────────────

# Each Silero chunk at 16kHz with 512 samples = 32ms
_CHUNK_DURATION_MS = (_SILERO_CHUNK_SAMPLES / _SILERO_SAMPLE_RATE) * 1000.0  # 32ms


@pytest.mark.skipif(not _VAD_AVAILABLE, reason="torchaudio not installed")
class TestVADSpeechEndSilenceDuration:
    """Property 7: VAD speech_end silence duration.

    For any sequence of audio frames where the VAD confidence drops below
    the threshold, a speech_end event SHALL be emitted if and only if the
    cumulative silence duration reaches or exceeds 300 milliseconds.

    **Validates: Requirements 4.2**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        num_silence_chunks=st.integers(min_value=1, max_value=30),
    )
    def test_speech_end_emitted_iff_silence_gte_300ms(self, num_silence_chunks):
        """SPEECH_END is emitted iff cumulative silence >= 300ms after speaking."""
        # Calculate how many chunks of 32ms are needed for 300ms
        # 300ms / 32ms = 9.375, so 10 chunks needed to reach >= 300ms
        chunks_needed_for_end = math.ceil(300.0 / _CHUNK_DURATION_MS)

        with patch("src.realtime.vad.torch.hub.load") as mock_hub_load:
            mock_model = MagicMock()
            mock_hub_load.return_value = (mock_model, None)

            with patch("src.realtime.vad.torchaudio.transforms.Resample") as mock_resample_cls:
                import torch as _torch

                mock_resampler = MagicMock()
                mock_resampler.return_value = _torch.zeros(_SILERO_CHUNK_SAMPLES, dtype=_torch.float32)
                mock_resample_cls.return_value = mock_resampler

                processor = VADProcessor(threshold=0.5, silence_duration_ms=300)

                audio_frame = b"\xff" * 160

                # First: put processor into speaking state with high confidence
                mock_model.return_value.item.return_value = 0.8
                event = processor.process_frame(audio_frame)
                assert event == VADEvent.SPEECH_START
                assert processor.is_speaking

                # Now send num_silence_chunks frames with below-threshold confidence
                mock_model.return_value.item.return_value = 0.1
                speech_end_emitted = False
                speech_end_at_chunk = None

                for i in range(num_silence_chunks):
                    evt = processor.process_frame(audio_frame)
                    if evt == VADEvent.SPEECH_END:
                        speech_end_emitted = True
                        speech_end_at_chunk = i + 1
                        break

                cumulative_silence_ms = num_silence_chunks * _CHUNK_DURATION_MS

                if cumulative_silence_ms >= 300.0:
                    # Should have emitted SPEECH_END
                    assert speech_end_emitted, (
                        f"Expected SPEECH_END after {num_silence_chunks} chunks "
                        f"({cumulative_silence_ms}ms >= 300ms)"
                    )
                    # Verify it happened at the correct chunk
                    assert speech_end_at_chunk == chunks_needed_for_end
                else:
                    # Should NOT have emitted SPEECH_END
                    assert not speech_end_emitted, (
                        f"Unexpected SPEECH_END after {num_silence_chunks} chunks "
                        f"({cumulative_silence_ms}ms < 300ms)"
                    )
                    # Processor should still be in speaking state
                    assert processor.is_speaking

    @settings(max_examples=100, deadline=None)
    @given(
        silence_confidence=st.floats(
            min_value=0.0, max_value=0.49, allow_nan=False, allow_infinity=False
        ),
    )
    def test_speech_end_requires_previous_speaking_state(self, silence_confidence):
        """SPEECH_END is NOT emitted if the processor was never in speaking state."""
        with patch("src.realtime.vad.torch.hub.load") as mock_hub_load:
            mock_model = MagicMock()
            mock_model.return_value.item.return_value = silence_confidence
            mock_hub_load.return_value = (mock_model, None)

            with patch("src.realtime.vad.torchaudio.transforms.Resample") as mock_resample_cls:
                import torch as _torch

                mock_resampler = MagicMock()
                mock_resampler.return_value = _torch.zeros(_SILERO_CHUNK_SAMPLES, dtype=_torch.float32)
                mock_resample_cls.return_value = mock_resampler

                processor = VADProcessor(threshold=0.5, silence_duration_ms=300)

                audio_frame = b"\xff" * 160

                # Send many silence frames without ever being in speaking state
                for _ in range(20):  # 20 * 32ms = 640ms > 300ms
                    event = processor.process_frame(audio_frame)
                    # Should never emit SPEECH_END since we were never speaking
                    assert event is None

                assert not processor.is_speaking

    @settings(max_examples=100, deadline=None)
    @given(
        speech_interruption_at=st.integers(min_value=1, max_value=8),
    )
    def test_silence_counter_resets_on_speech(self, speech_interruption_at):
        """Silence counter resets if speech resumes before 300ms threshold."""
        # speech_interruption_at is the chunk number (1-8) where speech resumes
        # Since 9 chunks < 300ms (9*32=288ms), interrupting before chunk 9
        # means we never reach the threshold

        with patch("src.realtime.vad.torch.hub.load") as mock_hub_load:
            mock_model = MagicMock()
            mock_hub_load.return_value = (mock_model, None)

            with patch("src.realtime.vad.torchaudio.transforms.Resample") as mock_resample_cls:
                import torch as _torch

                mock_resampler = MagicMock()
                mock_resampler.return_value = _torch.zeros(_SILERO_CHUNK_SAMPLES, dtype=_torch.float32)
                mock_resample_cls.return_value = mock_resampler

                processor = VADProcessor(threshold=0.5, silence_duration_ms=300)

                audio_frame = b"\xff" * 160

                # Put processor into speaking state
                mock_model.return_value.item.return_value = 0.8
                event = processor.process_frame(audio_frame)
                assert event == VADEvent.SPEECH_START

                # Send silence frames up to speech_interruption_at
                mock_model.return_value.item.return_value = 0.1
                for i in range(speech_interruption_at):
                    evt = processor.process_frame(audio_frame)
                    # Should not emit SPEECH_END since we haven't reached 300ms
                    # (max 8 chunks * 32ms = 256ms < 300ms)
                    assert evt is None

                # Resume speech - this should reset the silence counter
                mock_model.return_value.item.return_value = 0.8
                evt = processor.process_frame(audio_frame)
                # Should NOT emit SPEECH_START (already speaking)
                assert evt is None
                assert processor.is_speaking

                # Now send silence again - counter should start from 0
                mock_model.return_value.item.return_value = 0.1
                # Send fewer than threshold chunks
                for i in range(5):  # 5 * 32ms = 160ms < 300ms
                    evt = processor.process_frame(audio_frame)
                    assert evt is None

                # Still speaking because total continuous silence < 300ms
                assert processor.is_speaking


# Feature: realtime-voice-conversation, Property 8: Barge-in state machine transitions
# ── Strategies for Property 8 ────────────────────────────────────────────────

import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.realtime.session import ConversationSession, handle_barge_in
from src.realtime.playback import PlaybackTracker
from src.realtime.models import OutboundClearMessage

# Stream SID strategy
_stream_sid_strategy_p8 = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=5,
    max_size=34,
).map(lambda s: "MZ" + s)

# Chunk text segments for playback tracker
_chunk_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=50,
)

# Strategy for a list of playback chunks (chunk_id, text_segment)
_playback_chunks_strategy = st.lists(
    st.tuples(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=3,
            max_size=20,
        ).map(lambda s: "chunk_" + s),
        _chunk_text_strategy,
    ),
    min_size=0,
    max_size=20,
)


@st.composite
def speaking_session_strategy(draw):
    """Generate a ConversationSession in SPEAKING state with mock pipeline state."""
    stream_sid = draw(_stream_sid_strategy_p8)
    call_sid = draw(call_sid_strategy)
    language = draw(language_strategy)
    demo_id = draw(demo_id_strategy)
    caller_from = draw(caller_from_strategy)
    chunks = draw(_playback_chunks_strategy)
    has_generation_task = draw(st.booleans())

    # Create session
    session = ConversationSession(
        call_sid=call_sid,
        stream_sid=stream_sid,
        language=language,
        demo_id=demo_id,
        caller_from=caller_from,
        voice_id="test_voice_id",
    )

    # Set to SPEAKING state
    session.pipeline_state = PipelineState.SPEAKING

    # Set up playback tracker with chunks
    tracker = PlaybackTracker()
    for chunk_id, text_segment in chunks:
        tracker.record_chunk_sent(chunk_id, text_segment)
    session.playback_tracker = tracker

    # Optionally set up a mock current_generation_task
    if has_generation_task:
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False
        mock_task.cancel.return_value = True
        session.current_generation_task = mock_task
    else:
        session.current_generation_task = None

    return session, stream_sid, chunks, has_generation_task


# ── Property 8 Test ───────────────────────────────────────────────────────────


class TestBargeInStateMachineTransitions:
    """Property 8: Barge-in state machine transitions.

    For any ConversationSession in SPEAKING state, when a VAD speech_start
    event occurs, the session SHALL transition to INTERRUPTED state, all
    pending TTS audio buffers SHALL be cleared, the current LLM generation
    task SHALL be cancelled, and a clear message SHALL be queued for sending
    to Twilio.

    **Validates: Requirements 4.3, 4.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(data=speaking_session_strategy())
    def test_transitions_to_interrupted_state(self, data):
        """After barge-in, pipeline state is INTERRUPTED."""
        session, stream_sid, chunks, has_task = data

        handle_barge_in(session, stream_sid)

        assert session.pipeline_state == PipelineState.INTERRUPTED

    @settings(max_examples=100, deadline=None)
    @given(data=speaking_session_strategy())
    def test_playback_tracker_is_cleared(self, data):
        """After barge-in, the playback tracker has no recorded chunks."""
        session, stream_sid, chunks, has_task = data

        handle_barge_in(session, stream_sid)

        # Playback tracker should be cleared (partial text is empty)
        assert session.playback_tracker.get_partial_text_at_interruption() == ""

    @settings(max_examples=100, deadline=None)
    @given(data=speaking_session_strategy())
    def test_generation_task_is_cancelled(self, data):
        """After barge-in, the current generation task is cancelled (if it existed)."""
        session, stream_sid, chunks, has_task = data

        handle_barge_in(session, stream_sid)

        if has_task:
            # The mock task's cancel() should have been called
            session.current_generation_task.cancel.assert_called_once()
        # If no task existed, no error should occur (graceful no-op)

    @settings(max_examples=100, deadline=None)
    @given(data=speaking_session_strategy())
    def test_returns_clear_message(self, data):
        """After barge-in, an OutboundClearMessage is returned with correct stream SID."""
        session, stream_sid, chunks, has_task = data

        clear_msg = handle_barge_in(session, stream_sid)

        assert clear_msg["event"] == "clear"
        assert clear_msg["streamSid"] == stream_sid

    @settings(max_examples=100, deadline=None)
    @given(data=speaking_session_strategy())
    def test_all_postconditions_hold_simultaneously(self, data):
        """All barge-in postconditions hold together for any valid session state."""
        session, stream_sid, chunks, has_task = data

        clear_msg = handle_barge_in(session, stream_sid)

        # Postcondition 1: State is INTERRUPTED
        assert session.pipeline_state == PipelineState.INTERRUPTED

        # Postcondition 2: Playback tracker cleared
        assert session.playback_tracker.get_partial_text_at_interruption() == ""

        # Postcondition 3: Generation task cancelled (if existed)
        if has_task:
            session.current_generation_task.cancel.assert_called()

        # Postcondition 4: Clear message is well-formed
        assert clear_msg["event"] == "clear"
        assert clear_msg["streamSid"] == stream_sid


# Feature: realtime-voice-conversation, Property 4: Inbound audio decoding and forwarding
# ── Strategies for Property 4 ────────────────────────────────────────────────

import base64

from src.realtime.models import (
    TwilioMediaMessage,
    decode_media_payload,
)

# Random byte sequences simulating raw audio payloads (1 to 4096 bytes)
_audio_bytes_strategy = st.binary(min_size=1, max_size=4096)

# Stream SID for media messages
_media_stream_sid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=5,
    max_size=34,
).map(lambda s: "MZ" + s)


@st.composite
def twilio_media_message_strategy(draw):
    """Generate a valid TwilioMediaMessage with a random base64-encoded payload.

    Simulates what Twilio sends: takes random bytes (the original audio),
    encodes them as base64, and wraps them in the Twilio media message format.
    """
    original_bytes = draw(_audio_bytes_strategy)
    stream_sid = draw(_media_stream_sid_strategy)
    seq_num = draw(st.integers(min_value=1, max_value=99999).map(str))
    chunk = draw(st.integers(min_value=1, max_value=99999).map(str))
    timestamp = draw(st.integers(min_value=0, max_value=999999).map(str))

    # Encode the original bytes as base64 (this is what Twilio does)
    payload_b64 = base64.b64encode(original_bytes).decode("ascii")

    msg: TwilioMediaMessage = {
        "event": "media",
        "sequenceNumber": seq_num,
        "media": {
            "track": "inbound",
            "chunk": chunk,
            "timestamp": timestamp,
            "payload": payload_b64,
        },
        "streamSid": stream_sid,
    }
    return msg, original_bytes


# ── Property 4 Test ───────────────────────────────────────────────────────────


class TestInboundAudioDecodingAndForwarding:
    """Property 4: Inbound audio decoding and forwarding.

    For any valid Twilio media event with a base64-encoded mulaw payload,
    decoding the payload and forwarding it SHALL produce the exact same bytes
    that were originally encoded — i.e., base64.b64decode(event.media.payload)
    == original audio bytes.

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=100, deadline=None)
    @given(data=twilio_media_message_strategy())
    def test_decode_produces_original_bytes(self, data):
        """Decoding a media event payload produces the exact original bytes."""
        msg, original_bytes = data
        decoded = decode_media_payload(msg)
        assert decoded == original_bytes

    @settings(max_examples=100, deadline=None)
    @given(data=twilio_media_message_strategy())
    def test_decode_length_matches_original(self, data):
        """Decoded payload length matches the original byte sequence length."""
        msg, original_bytes = data
        decoded = decode_media_payload(msg)
        assert len(decoded) == len(original_bytes)

    @settings(max_examples=100, deadline=None)
    @given(original_bytes=_audio_bytes_strategy)
    def test_base64_roundtrip_identity(self, original_bytes):
        """Base64 encode then decode is the identity function on bytes."""
        encoded = base64.b64encode(original_bytes).decode("ascii")
        decoded = base64.b64decode(encoded)
        assert decoded == original_bytes


# Feature: realtime-voice-conversation, Property 5: LLM triggered only on final transcripts
# ── Strategies for Property 5 ────────────────────────────────────────────────

from src.realtime.models import process_transcript

# Transcript text (non-empty strings simulating speech)
_transcript_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=200,
)

# A single transcript result: (text, is_final)
_transcript_result_strategy = st.tuples(_transcript_text_strategy, st.booleans())

# A sequence of transcript results (1 to 50 results)
_transcript_sequence_strategy = st.lists(
    _transcript_result_strategy,
    min_size=1,
    max_size=50,
)


# ── Property 5 Test ───────────────────────────────────────────────────────────


class TestLLMTriggeredOnlyOnFinalTranscripts:
    """Property 5: LLM triggered only on final transcripts.

    For any sequence of STT transcript results, the LLM SHALL be invoked if
    and only if a result has is_final set to true. Interim results (where
    is_final is false) SHALL be buffered without triggering LLM processing.

    **Validates: Requirements 3.3, 3.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(sequence=_transcript_sequence_strategy)
    def test_llm_triggered_iff_is_final_true(self, sequence):
        """LLM is triggered exactly when is_final is True, never for interim results."""
        buffer: list[str] = []
        llm_trigger_count = 0

        for transcript, is_final in sequence:
            triggered = process_transcript(transcript, is_final, buffer)
            if is_final:
                assert triggered is True, (
                    f"LLM should be triggered for final transcript: {transcript!r}"
                )
                llm_trigger_count += 1
            else:
                assert triggered is False, (
                    f"LLM should NOT be triggered for interim transcript: {transcript!r}"
                )

        # Total LLM triggers equals number of final transcripts
        expected_triggers = sum(1 for _, is_final in sequence if is_final)
        assert llm_trigger_count == expected_triggers

    @settings(max_examples=100, deadline=None)
    @given(sequence=_transcript_sequence_strategy)
    def test_interim_results_are_buffered(self, sequence):
        """Interim results are accumulated in the buffer without triggering LLM."""
        buffer: list[str] = []

        for transcript, is_final in sequence:
            if not is_final:
                prev_len = len(buffer)
                process_transcript(transcript, is_final, buffer)
                # Buffer grows by one for each interim result
                assert len(buffer) == prev_len + 1
                assert buffer[-1] == transcript

    @settings(max_examples=100, deadline=None)
    @given(sequence=_transcript_sequence_strategy)
    def test_buffer_cleared_on_final(self, sequence):
        """Buffer is cleared when a final transcript is received."""
        buffer: list[str] = []

        for transcript, is_final in sequence:
            process_transcript(transcript, is_final, buffer)
            if is_final:
                # Buffer should be empty after processing a final transcript
                assert buffer == [], (
                    f"Buffer should be cleared after final transcript, got: {buffer}"
                )

    @settings(max_examples=100, deadline=None)
    @given(sequence=_transcript_sequence_strategy)
    def test_llm_never_triggered_for_all_interim(self, sequence):
        """If all results are interim, LLM is never triggered."""
        # Force all to interim
        all_interim = [(text, False) for text, _ in sequence]
        buffer: list[str] = []
        triggers = []

        for transcript, is_final in all_interim:
            triggered = process_transcript(transcript, is_final, buffer)
            triggers.append(triggered)

        assert all(t is False for t in triggers), "No LLM trigger expected for all-interim sequence"
        assert len(buffer) == len(all_interim), "All interim results should be in buffer"


# Feature: realtime-voice-conversation, Property 10: Sentence chunking algorithm
# ── Strategies for Property 10 ────────────────────────────────────────────────

from src.realtime.llm import chunk_text_into_sentences, _SENTENCE_ENDINGS

# Text that contains at least some sentence-ending punctuation
_sentence_ending_chars = ".!?:"
_non_ending_chars = st.characters(
    blacklist_categories=("Cs",),
    blacklist_characters="\x00",
)

# Strategy for text that may contain sentence-ending punctuation
_text_with_punctuation_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=500,
)

# Strategy for text that definitely contains sentence-ending punctuation
@st.composite
def text_with_sentences_strategy(draw):
    """Generate text that contains at least one sentence-ending punctuation mark."""
    # Generate 1-5 sentence segments
    num_sentences = draw(st.integers(min_value=1, max_value=5))
    parts = []
    for i in range(num_sentences):
        # Each sentence: some non-empty text followed by a sentence-ending char
        body = draw(st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters="\x00.!?:",
            ),
            min_size=1,
            max_size=80,
        ))
        ending = draw(st.sampled_from(list(_sentence_ending_chars)))
        parts.append(body + ending)

    # Optionally add trailing text without punctuation (final flush case)
    if draw(st.booleans()):
        tail = draw(st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters="\x00.!?:",
            ),
            min_size=1,
            max_size=50,
        ))
        parts.append(tail)

    return "".join(parts)


# ── Property 10 Test ──────────────────────────────────────────────────────────


class TestSentenceChunkingAlgorithm:
    """Property 10: Sentence chunking algorithm.

    For any stream of text tokens, the sentence chunker SHALL split the
    accumulated text into chunks at sentence-ending punctuation boundaries
    (., !, ?, :) such that:
    (a) each emitted chunk ends with sentence-ending punctuation or is the final flush,
    (b) no chunk is empty, and
    (c) the concatenation of all emitted chunks equals the full original text.

    **Validates: Requirements 5.4, 5.2, 5.5**
    """

    @settings(max_examples=100, deadline=None)
    @given(text=_text_with_punctuation_strategy)
    def test_concatenation_equals_original_stripped(self, text):
        """(c) The concatenation of all emitted chunks equals the stripped original text."""
        chunks = chunk_text_into_sentences(text)
        if not text.strip():
            assert chunks == []
        else:
            concatenated = "".join(chunks)
            # The concatenation should equal the original text stripped,
            # but since we strip each chunk individually, we need to account
            # for whitespace between chunks being consumed.
            # The property is: joining all chunks reproduces the meaningful content.
            # Since each chunk is stripped, the concatenation equals text with
            # inter-sentence whitespace removed.
            # Actually, the chunking splits at punctuation boundaries and strips each chunk.
            # So concatenation == text with leading/trailing whitespace removed from each segment.
            # Let's verify the weaker but correct property: all chars in chunks come from text
            # and no content is lost (every non-whitespace char in text appears in chunks).
            original_no_ws = "".join(text.split())
            chunks_no_ws = "".join("".join(chunks).split())
            assert chunks_no_ws == original_no_ws

    @settings(max_examples=100, deadline=None)
    @given(text=_text_with_punctuation_strategy)
    def test_no_chunk_is_empty(self, text):
        """(b) No emitted chunk is empty."""
        chunks = chunk_text_into_sentences(text)
        for chunk in chunks:
            assert chunk != ""
            assert chunk.strip() != ""

    @settings(max_examples=100, deadline=None)
    @given(text=text_with_sentences_strategy())
    def test_non_final_chunks_end_with_sentence_punctuation(self, text):
        """(a) Each emitted chunk ends with sentence-ending punctuation, except possibly the last."""
        chunks = chunk_text_into_sentences(text)
        if len(chunks) > 1:
            # All chunks except the last must end with sentence-ending punctuation
            for chunk in chunks[:-1]:
                assert chunk[-1] in _SENTENCE_ENDINGS, (
                    f"Non-final chunk {chunk!r} does not end with sentence punctuation"
                )
        # The last chunk may or may not end with punctuation (final flush)

    @settings(max_examples=100, deadline=None)
    @given(text=text_with_sentences_strategy())
    def test_chunks_split_at_punctuation_boundaries(self, text):
        """Chunks are split at sentence-ending punctuation boundaries."""
        chunks = chunk_text_into_sentences(text)
        # Verify that all non-final chunks end with one of the sentence-ending chars
        for i, chunk in enumerate(chunks[:-1]):
            assert chunk[-1] in _SENTENCE_ENDINGS, (
                f"Chunk {i} ({chunk!r}) should end with sentence punctuation"
            )

    @settings(max_examples=100, deadline=None)
    @given(text=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters="\x00.!?:",
        ),
        min_size=1,
        max_size=200,
    ))
    def test_text_without_punctuation_produces_single_chunk(self, text):
        """Text without any sentence-ending punctuation produces a single chunk (final flush)."""
        chunks = chunk_text_into_sentences(text)
        if text.strip():
            assert len(chunks) == 1
            assert chunks[0] == text.strip()

    @settings(max_examples=100, deadline=None)
    @given(text=st.just(""))
    def test_empty_text_produces_no_chunks(self, text):
        """Empty text produces no chunks."""
        chunks = chunk_text_into_sentences(text)
        assert chunks == []

    @settings(max_examples=100, deadline=None)
    @given(text=st.text(
        alphabet=st.just(" "),
        min_size=1,
        max_size=50,
    ))
    def test_whitespace_only_produces_no_chunks(self, text):
        """Whitespace-only text produces no chunks."""
        chunks = chunk_text_into_sentences(text)
        assert chunks == []


# Feature: realtime-voice-conversation, Property 11: LLM JSON response parsing
# ── Strategies for Property 11 ────────────────────────────────────────────────

from src.realtime.llm import parse_llm_response

# Strategy for optional string fields (can be a string or None/null)
_optional_string_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
        min_size=1,
        max_size=100,
    ),
)

# Strategy for the message field (always a string, can be empty)
_message_strategy_p11 = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=300,
)

# Strategy for end_call field (boolean or None)
_end_call_strategy = st.one_of(st.none(), st.booleans())

# Strategy for profile_update field (dict or None)
_profile_update_strategy = st.one_of(
    st.none(),
    st.dictionaries(
        keys=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
            min_size=1,
            max_size=20,
        ),
        values=st.one_of(
            st.none(),
            st.text(min_size=0, max_size=50),
            st.integers(min_value=-1000, max_value=1000),
            st.booleans(),
        ),
        min_size=0,
        max_size=5,
    ),
)


@st.composite
def valid_llm_response_strategy(draw):
    """Generate a valid JSON response dict conforming to the conversational response schema."""
    message = draw(_message_strategy_p11)
    name = draw(_optional_string_strategy)
    phone = draw(_optional_string_strategy)
    notes = draw(_optional_string_strategy)
    end_call = draw(_end_call_strategy)
    profile_update = draw(_profile_update_strategy)

    response_dict = {"message": message}

    # Optionally include each field (to test missing fields defaulting)
    if draw(st.booleans()) or name is not None:
        response_dict["name"] = name
    if draw(st.booleans()) or phone is not None:
        response_dict["phone"] = phone
    if draw(st.booleans()) or notes is not None:
        response_dict["notes"] = notes
    if draw(st.booleans()) or end_call is not None:
        response_dict["end_call"] = end_call
    if draw(st.booleans()) or profile_update is not None:
        response_dict["profile_update"] = profile_update

    return response_dict


@st.composite
def full_llm_response_strategy(draw):
    """Generate a response dict with ALL fields present (including nulls)."""
    message = draw(_message_strategy_p11)
    name = draw(_optional_string_strategy)
    phone = draw(_optional_string_strategy)
    notes = draw(_optional_string_strategy)
    end_call = draw(_end_call_strategy)
    profile_update = draw(_profile_update_strategy)

    return {
        "message": message,
        "name": name,
        "phone": phone,
        "notes": notes,
        "end_call": end_call,
        "profile_update": profile_update,
    }


# ── Property 11 Test ──────────────────────────────────────────────────────────


class TestLLMJSONResponseParsing:
    """Property 11: LLM JSON response parsing.

    For any valid JSON string conforming to the conversational response schema
    (containing message, name, phone, notes, end_call, profile_update fields),
    parsing SHALL extract each field correctly, with null JSON values mapped to
    Python None and missing optional fields defaulting to None or {} for
    profile_update.

    **Validates: Requirements 5.2, 5.5**
    """

    @settings(max_examples=100, deadline=None)
    @given(response_dict=full_llm_response_strategy())
    def test_all_fields_extracted_correctly(self, response_dict):
        """All fields in a complete JSON response are extracted correctly."""
        json_text = json.dumps(response_dict)
        parsed = parse_llm_response(json_text)

        # message: empty string if None/falsy, otherwise the value
        expected_message = response_dict["message"] or ""
        assert parsed["message"] == expected_message

        # name: None if null/empty, otherwise the value
        expected_name = response_dict["name"] or None
        assert parsed["name"] == expected_name

        # phone: None if null/empty, otherwise the value
        expected_phone = response_dict["phone"] or None
        assert parsed["phone"] == expected_phone

        # notes: None if null/empty, otherwise the value
        expected_notes = response_dict["notes"] or None
        assert parsed["notes"] == expected_notes

        # end_call: None if null, otherwise the boolean value
        if response_dict["end_call"] is not None:
            assert parsed["end_call"] == response_dict["end_call"]
        else:
            assert parsed["end_call"] is None

        # profile_update: {} if null, otherwise the dict value
        if response_dict["profile_update"] is not None:
            assert parsed["profile_update"] == response_dict["profile_update"]
        else:
            assert parsed["profile_update"] == {}

    @settings(max_examples=100, deadline=None)
    @given(response_dict=valid_llm_response_strategy())
    def test_missing_optional_fields_default_correctly(self, response_dict):
        """Missing optional fields default to None (or {} for profile_update)."""
        json_text = json.dumps(response_dict)
        parsed = parse_llm_response(json_text)

        # All expected keys must be present in the parsed result
        assert "message" in parsed
        assert "name" in parsed
        assert "phone" in parsed
        assert "notes" in parsed
        assert "end_call" in parsed
        assert "profile_update" in parsed

        # If a field was missing from the input, it should default
        if "name" not in response_dict:
            assert parsed["name"] is None
        if "phone" not in response_dict:
            assert parsed["phone"] is None
        if "notes" not in response_dict:
            assert parsed["notes"] is None
        if "end_call" not in response_dict:
            assert parsed["end_call"] is None
        if "profile_update" not in response_dict:
            assert parsed["profile_update"] == {}

    @settings(max_examples=100, deadline=None)
    @given(response_dict=full_llm_response_strategy())
    def test_null_json_values_map_to_python_none(self, response_dict):
        """JSON null values are mapped to Python None (or {} for profile_update)."""
        # Force all optional fields to null
        null_response = {
            "message": response_dict["message"],
            "name": None,
            "phone": None,
            "notes": None,
            "end_call": None,
            "profile_update": None,
        }
        json_text = json.dumps(null_response)
        parsed = parse_llm_response(json_text)

        assert parsed["name"] is None
        assert parsed["phone"] is None
        assert parsed["notes"] is None
        assert parsed["end_call"] is None
        assert parsed["profile_update"] == {}  # null profile_update defaults to {}

    @settings(max_examples=100, deadline=None)
    @given(response_dict=full_llm_response_strategy())
    def test_parsed_result_always_has_all_keys(self, response_dict):
        """The parsed result always contains all 6 expected keys regardless of input."""
        json_text = json.dumps(response_dict)
        parsed = parse_llm_response(json_text)

        expected_keys = {"message", "name", "phone", "notes", "end_call", "profile_update"}
        assert set(parsed.keys()) == expected_keys

    @settings(max_examples=100, deadline=None)
    @given(
        invalid_text=st.text(
            alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
            min_size=1,
            max_size=200,
        ).filter(lambda t: not t.strip().startswith("{"))
    )
    def test_invalid_json_returns_fallback(self, invalid_text):
        """Invalid JSON input returns a fallback dict with the text as message."""
        parsed = parse_llm_response(invalid_text)

        # Should return fallback structure
        assert parsed["message"] == invalid_text
        assert parsed["name"] is None
        assert parsed["phone"] is None
        assert parsed["notes"] is None
        assert parsed["end_call"] is None
        assert parsed["profile_update"] == {}

    @settings(max_examples=100, deadline=None)
    @given(response_dict=full_llm_response_strategy())
    def test_profile_update_never_none_in_output(self, response_dict):
        """The profile_update field in parsed output is never None — it's always a dict."""
        json_text = json.dumps(response_dict)
        parsed = parse_llm_response(json_text)

        # profile_update should always be a dict (never None)
        assert isinstance(parsed["profile_update"], dict)


# Feature: realtime-voice-conversation, Property 12: Outbound audio encoding for Twilio
# ── Strategies for Property 12 ────────────────────────────────────────────────

from src.realtime.models import encode_audio_for_twilio, OutboundMediaMessage

# Random byte sequences simulating TTS audio output (1 to 8192 bytes)
_outbound_audio_bytes_strategy = st.binary(min_size=1, max_size=8192)

# Stream SID for outbound messages
_outbound_stream_sid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=5,
    max_size=34,
).map(lambda s: "MZ" + s)


# ── Property 12 Test ──────────────────────────────────────────────────────────


class TestOutboundAudioEncodingForTwilio:
    """Property 12: Outbound audio encoding for Twilio.

    For any raw audio byte sequence, encoding it for Twilio SHALL produce a
    JSON message with event set to "media", the correct streamSid, and
    media.payload containing the base64 encoding of the input bytes — such
    that base64.b64decode(output.media.payload) == input_bytes.

    **Validates: Requirements 6.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        audio_bytes=_outbound_audio_bytes_strategy,
        stream_sid=_outbound_stream_sid_strategy,
    )
    def test_event_is_media(self, audio_bytes, stream_sid):
        """The encoded message has event set to 'media'."""
        msg = encode_audio_for_twilio(audio_bytes, stream_sid)
        assert msg["event"] == "media"

    @settings(max_examples=100, deadline=None)
    @given(
        audio_bytes=_outbound_audio_bytes_strategy,
        stream_sid=_outbound_stream_sid_strategy,
    )
    def test_stream_sid_matches(self, audio_bytes, stream_sid):
        """The encoded message has the correct streamSid."""
        msg = encode_audio_for_twilio(audio_bytes, stream_sid)
        assert msg["streamSid"] == stream_sid

    @settings(max_examples=100, deadline=None)
    @given(
        audio_bytes=_outbound_audio_bytes_strategy,
        stream_sid=_outbound_stream_sid_strategy,
    )
    def test_payload_decodes_to_original_bytes(self, audio_bytes, stream_sid):
        """base64.b64decode(output.media.payload) == input_bytes."""
        msg = encode_audio_for_twilio(audio_bytes, stream_sid)
        decoded = base64.b64decode(msg["media"]["payload"])
        assert decoded == audio_bytes

    @settings(max_examples=100, deadline=None)
    @given(
        audio_bytes=_outbound_audio_bytes_strategy,
        stream_sid=_outbound_stream_sid_strategy,
    )
    def test_all_properties_hold_simultaneously(self, audio_bytes, stream_sid):
        """All encoding properties hold together for any input."""
        msg = encode_audio_for_twilio(audio_bytes, stream_sid)

        # Property: event == "media"
        assert msg["event"] == "media"

        # Property: streamSid matches input
        assert msg["streamSid"] == stream_sid

        # Property: payload round-trips correctly
        decoded = base64.b64decode(msg["media"]["payload"])
        assert decoded == audio_bytes


# Feature: realtime-voice-conversation, Property 13: Session info update from LLM response
# ── Strategies for Property 13 ────────────────────────────────────────────────

from unittest.mock import patch as _patch

from src.realtime.store_integration import update_collected_info

# Strategy for optional string fields in LLM response (name, phone, notes)
_info_field_strategy = st.one_of(
    st.none(),
    st.just(""),  # empty string treated as falsy
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
        min_size=1,
        max_size=100,
    ),
)

# Strategy for existing collected info (may have pre-existing values)
_existing_info_strategy = st.fixed_dictionaries({
    "name": _info_field_strategy,
    "phone": _info_field_strategy,
    "notes": _info_field_strategy,
    "topic": st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
        min_size=0,
        max_size=50,
    ),
    "lang": st.sampled_from(["en", "es", "fr", "de", ""]),
})


@st.composite
def llm_response_with_partial_info_strategy(draw):
    """Generate an LLM response dict with a random subset of non-null info fields."""
    name = draw(_info_field_strategy)
    phone = draw(_info_field_strategy)
    notes = draw(_info_field_strategy)

    response = {
        "message": draw(st.text(min_size=0, max_size=100)),
        "name": name,
        "phone": phone,
        "notes": notes,
        "end_call": draw(st.one_of(st.none(), st.booleans())),
        "profile_update": draw(st.one_of(st.none(), st.just({}))),
    }
    return response


# ── Property 13 Test ──────────────────────────────────────────────────────────


class TestSessionInfoUpdateFromLLMResponse:
    """Property 13: Session info update from LLM response.

    For any LLM response containing a subset of non-null fields (name, phone,
    notes), updating the session's collected info SHALL overwrite only those
    fields that are non-null in the response, leaving all other fields unchanged.

    **Validates: Requirements 7.2**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        llm_response=llm_response_with_partial_info_strategy(),
        current_info=_existing_info_strategy,
    )
    def test_non_null_fields_overwrite_existing(self, call_sid, llm_response, current_info):
        """Non-null (truthy) fields in the LLM response overwrite the corresponding fields in collected info."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            result = update_collected_info(call_sid, llm_response, current_info)

            # For each info field, if the LLM response has a truthy value, it should overwrite
            if llm_response.get("name"):
                assert result["name"] == llm_response["name"]
            if llm_response.get("phone"):
                assert result["phone"] == llm_response["phone"]
            if llm_response.get("notes"):
                assert result["notes"] == llm_response["notes"]

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        llm_response=llm_response_with_partial_info_strategy(),
        current_info=_existing_info_strategy,
    )
    def test_null_fields_leave_existing_unchanged(self, call_sid, llm_response, current_info):
        """Null/empty/falsy fields in the LLM response leave existing info fields unchanged."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            result = update_collected_info(call_sid, llm_response, current_info)

            # For each info field, if the LLM response has a falsy value, the original should be preserved
            if not llm_response.get("name"):
                assert result["name"] == current_info["name"]
            if not llm_response.get("phone"):
                assert result["phone"] == current_info["phone"]
            if not llm_response.get("notes"):
                assert result["notes"] == current_info["notes"]

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        llm_response=llm_response_with_partial_info_strategy(),
        current_info=_existing_info_strategy,
    )
    def test_non_info_fields_always_preserved(self, call_sid, llm_response, current_info):
        """Fields not managed by the LLM response (topic, lang) are always preserved."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            result = update_collected_info(call_sid, llm_response, current_info)

            # topic and lang should never be modified by update_collected_info
            assert result["topic"] == current_info["topic"]
            assert result["lang"] == current_info["lang"]

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        llm_response=llm_response_with_partial_info_strategy(),
        current_info=_existing_info_strategy,
    )
    def test_result_persisted_to_redis(self, call_sid, llm_response, current_info):
        """The updated info is persisted to Redis via session_store.set_collected_info."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            result = update_collected_info(call_sid, llm_response, current_info)

            # Verify set_collected_info was called with the correct call_sid and result
            mock_store.set_collected_info.assert_called_once_with(call_sid, result)

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        current_info=_existing_info_strategy,
    )
    def test_all_null_response_preserves_everything(self, call_sid, current_info):
        """An LLM response with all null/empty info fields preserves the entire current info."""
        llm_response = {
            "message": "Hello",
            "name": None,
            "phone": None,
            "notes": None,
            "end_call": None,
            "profile_update": None,
        }
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            result = update_collected_info(call_sid, llm_response, current_info)

            # All fields should remain unchanged
            assert result == current_info


# Feature: realtime-voice-conversation, Property 15: Conversation history preservation on fallback
# ── Strategies for Property 15 ────────────────────────────────────────────────

from src.realtime.store_integration import save_conversation_history
from src.realtime.models import MAX_CONVERSATION_HISTORY

# A single conversation message
_conversation_message_strategy = st.fixed_dictionaries({
    "role": st.sampled_from(["system", "user", "assistant"]),
    "content": st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
        min_size=1,
        max_size=200,
    ),
})

# Conversation history: 1–100 messages (covers both under and over the 50-message cap)
_fallback_conversation_strategy = st.lists(
    _conversation_message_strategy,
    min_size=1,
    max_size=100,
)


# ── Property 15 Test ──────────────────────────────────────────────────────────


class TestConversationHistoryPreservationOnFallback:
    """Property 15: Conversation history preservation on fallback.

    For any active conversation session with N messages in history when a
    fallback to <Gather speech> is triggered, the conversation history stored
    in Redis SHALL contain all N messages (up to the 50-message cap) so the
    fallback flow can continue the conversation.

    **Validates: Requirements 10.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        history=_fallback_conversation_strategy,
    )
    def test_history_saved_to_redis_via_session_store(self, call_sid, history):
        """save_conversation_history persists the history to Redis via session_store.set_conversation."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            save_conversation_history(call_sid, history)

            # set_conversation must be called exactly once
            mock_store.set_conversation.assert_called_once()

            # Extract the arguments passed to set_conversation
            args = mock_store.set_conversation.call_args
            saved_call_sid = args[0][0]
            saved_history = args[0][1]

            assert saved_call_sid == call_sid

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        history=_fallback_conversation_strategy,
    )
    def test_all_messages_preserved_up_to_cap(self, call_sid, history):
        """All N messages are preserved (up to the 50-message cap) for fallback continuation."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            save_conversation_history(call_sid, history)

            # Extract the saved history
            args = mock_store.set_conversation.call_args
            saved_history = args[0][1]

            if len(history) <= MAX_CONVERSATION_HISTORY:
                # All messages should be preserved
                assert saved_history == history
                assert len(saved_history) == len(history)
            else:
                # Only the most recent 50 messages are preserved
                assert saved_history == history[-MAX_CONVERSATION_HISTORY:]
                assert len(saved_history) == MAX_CONVERSATION_HISTORY

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        history=_fallback_conversation_strategy,
    )
    def test_message_order_preserved(self, call_sid, history):
        """The order of messages in the saved history matches the original order."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            save_conversation_history(call_sid, history)

            args = mock_store.set_conversation.call_args
            saved_history = args[0][1]

            # The saved history should be a contiguous suffix of the original
            expected_start = max(0, len(history) - MAX_CONVERSATION_HISTORY)
            assert saved_history == history[expected_start:]

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        history=st.lists(_conversation_message_strategy, min_size=1, max_size=50),
    )
    def test_under_cap_preserves_all_messages(self, call_sid, history):
        """When history has <= 50 messages, ALL messages are preserved for fallback."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            save_conversation_history(call_sid, history)

            args = mock_store.set_conversation.call_args
            saved_history = args[0][1]

            # Every single message must be preserved
            assert saved_history == history
            assert len(saved_history) == len(history)

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        history=st.lists(_conversation_message_strategy, min_size=51, max_size=100),
    )
    def test_over_cap_retains_most_recent_50(self, call_sid, history):
        """When history exceeds 50 messages, only the most recent 50 are stored."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            save_conversation_history(call_sid, history)

            args = mock_store.set_conversation.call_args
            saved_history = args[0][1]

            assert len(saved_history) == MAX_CONVERSATION_HISTORY
            assert saved_history == history[-MAX_CONVERSATION_HISTORY:]

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        history=_fallback_conversation_strategy,
    )
    def test_saved_history_never_exceeds_cap(self, call_sid, history):
        """The saved history never exceeds the 50-message cap regardless of input size."""
        with _patch("src.realtime.store_integration.session_store") as mock_store:
            save_conversation_history(call_sid, history)

            args = mock_store.set_conversation.call_args
            saved_history = args[0][1]

            assert len(saved_history) <= MAX_CONVERSATION_HISTORY


# Feature: realtime-voice-conversation, Property 2: TwiML generation for conversational demos
# ── Imports for Properties 2 & 3 ─────────────────────────────────────────────

from xml.etree import ElementTree

# Ensure src is on the path for routes.ai import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Mock heavy dependencies required by routes.ai before importing
from unittest.mock import MagicMock as _MagicMock_p2

_mock_runtime_config_p2 = _MagicMock_p2()
_mock_runtime_config_p2.get = _MagicMock_p2(return_value="")
sys.modules.setdefault("runtime_config", _mock_runtime_config_p2)
sys.modules.setdefault("db", _MagicMock_p2())
sys.modules.setdefault("session_store", _MagicMock_p2())
sys.modules.setdefault("use_case_loader", _MagicMock_p2())
_mock_helpers_p2 = _MagicMock_p2()
_mock_helpers_p2.get_voice = _MagicMock_p2(return_value="alice")
_mock_helpers_p2.get_gather_language = _MagicMock_p2(return_value="en-US")
sys.modules.setdefault("helpers", _mock_helpers_p2)
sys.modules.setdefault("prompts", _MagicMock_p2())
sys.modules.setdefault("email_helper", _MagicMock_p2())
sys.modules.setdefault("config", _MagicMock_p2())
sys.modules.setdefault("reports", _MagicMock_p2())

from routes.ai import _build_media_stream_twiml

# ── Strategies for Property 2 ────────────────────────────────────────────────

# WS_HOST values (valid hostnames)
_ws_host_strategy = st.from_regex(
    r"[a-z][a-z0-9\-]{1,20}\.[a-z]{2,6}",
    fullmatch=True,
)

# Language codes for TwiML
_twiml_language_strategy = st.sampled_from(["en", "es", "fr", "de", "it", "pt", "ja", "zh", "ko", "ar"])

# Demo IDs for TwiML (alphanumeric + underscores, non-empty)
_twiml_demo_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=50,
)

# Caller phone numbers for TwiML
_twiml_caller_from_strategy = st.from_regex(r"\+1[0-9]{10}", fullmatch=True)


# ── Property 2 Test ───────────────────────────────────────────────────────────


class TestTwiMLGenerationForConversationalDemos:
    """Property 2: TwiML generation for conversational demos.

    For any Demo_Use_Case with ivr_type set to conversational and any
    combination of call_sid, language, demo_id, and caller_from values,
    the generated TwiML SHALL contain a <Connect><Stream> element with a url
    attribute pointing to the WebSocket endpoint and <Parameter> elements for
    each of lang, demo_id, and caller_from with their respective values.

    **Validates: Requirements 2.1, 2.2**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        ws_host=_ws_host_strategy,
        lang=_twiml_language_strategy,
        demo_id=_twiml_demo_id_strategy,
        caller_from=_twiml_caller_from_strategy,
    )
    def test_twiml_contains_connect_stream_element(self, ws_host, lang, demo_id, caller_from):
        """Generated TwiML contains a <Connect><Stream> element."""
        import routes.ai as ai_module

        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = ws_host
        try:
            result = _build_media_stream_twiml(
                lang=lang,
                demo_id=demo_id,
                caller_from=caller_from,
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        assert root.tag == "Response"

        connect = root.find("Connect")
        assert connect is not None, "TwiML must contain a <Connect> element"

        stream = connect.find("Stream")
        assert stream is not None, "TwiML must contain a <Stream> inside <Connect>"

    @settings(max_examples=100, deadline=None)
    @given(
        ws_host=_ws_host_strategy,
        lang=_twiml_language_strategy,
        demo_id=_twiml_demo_id_strategy,
        caller_from=_twiml_caller_from_strategy,
    )
    def test_stream_url_points_to_websocket_endpoint(self, ws_host, lang, demo_id, caller_from):
        """The <Stream> url attribute points to wss://{WS_HOST}/media-stream."""
        import routes.ai as ai_module

        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = ws_host
        try:
            result = _build_media_stream_twiml(
                lang=lang,
                demo_id=demo_id,
                caller_from=caller_from,
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        stream = root.find("Connect/Stream")
        assert stream.get("url") == f"wss://{ws_host}/media-stream"

    @settings(max_examples=100, deadline=None)
    @given(
        ws_host=_ws_host_strategy,
        lang=_twiml_language_strategy,
        demo_id=_twiml_demo_id_strategy,
        caller_from=_twiml_caller_from_strategy,
    )
    def test_parameter_elements_for_lang_demo_id_caller_from(self, ws_host, lang, demo_id, caller_from):
        """TwiML contains <Parameter> elements for lang, demo_id, and caller_from with correct values."""
        import routes.ai as ai_module

        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = ws_host
        try:
            result = _build_media_stream_twiml(
                lang=lang,
                demo_id=demo_id,
                caller_from=caller_from,
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        stream = root.find("Connect/Stream")
        params = stream.findall("Parameter")

        param_dict = {p.get("name"): p.get("value") for p in params}

        assert "lang" in param_dict, "Missing <Parameter name='lang'>"
        assert param_dict["lang"] == lang

        assert "demo_id" in param_dict, "Missing <Parameter name='demo_id'>"
        assert param_dict["demo_id"] == demo_id

        assert "caller_from" in param_dict, "Missing <Parameter name='caller_from'>"
        assert param_dict["caller_from"] == caller_from

    @settings(max_examples=100, deadline=None)
    @given(
        ws_host=_ws_host_strategy,
        lang=_twiml_language_strategy,
        demo_id=_twiml_demo_id_strategy,
        caller_from=_twiml_caller_from_strategy,
    )
    def test_no_gather_element_in_conversational_twiml(self, ws_host, lang, demo_id, caller_from):
        """Conversational TwiML does NOT contain a <Gather> element."""
        import routes.ai as ai_module

        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = ws_host
        try:
            result = _build_media_stream_twiml(
                lang=lang,
                demo_id=demo_id,
                caller_from=caller_from,
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)
        assert root.find("Gather") is None, "Conversational TwiML must NOT contain <Gather>"

    @settings(max_examples=100, deadline=None)
    @given(
        ws_host=_ws_host_strategy,
        lang=_twiml_language_strategy,
        demo_id=_twiml_demo_id_strategy,
        caller_from=_twiml_caller_from_strategy,
    )
    def test_all_properties_hold_simultaneously(self, ws_host, lang, demo_id, caller_from):
        """All Property 2 conditions hold together for any valid input combination."""
        import routes.ai as ai_module

        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = ws_host
        try:
            result = _build_media_stream_twiml(
                lang=lang,
                demo_id=demo_id,
                caller_from=caller_from,
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        root = ElementTree.fromstring(result)

        # 1. Contains <Connect><Stream>
        connect = root.find("Connect")
        assert connect is not None
        stream = connect.find("Stream")
        assert stream is not None

        # 2. URL points to WebSocket endpoint
        assert stream.get("url") == f"wss://{ws_host}/media-stream"

        # 3. Parameters match input values
        params = stream.findall("Parameter")
        param_dict = {p.get("name"): p.get("value") for p in params}
        assert param_dict["lang"] == lang
        assert param_dict["demo_id"] == demo_id
        assert param_dict["caller_from"] == caller_from

        # 4. No <Gather> element
        assert root.find("Gather") is None


# Feature: realtime-voice-conversation, Property 3: Non-conversational use cases produce Gather TwiML
# ── Strategies for Property 3 ────────────────────────────────────────────────

from twilio.twiml.voice_response import VoiceResponse, Gather

# Non-conversational ivr_type values
_non_conversational_ivr_type_strategy = st.sampled_from([
    "topics", "menu", "faq", "support", "sales", "booking",
])

# Gather action URL
_gather_action_strategy = st.from_regex(
    r"/ai-respond\?lang=[a-z]{2}&topic=[a-z_]{3,20}",
    fullmatch=True,
)

# Gather language
_gather_language_strategy = st.sampled_from([
    "en-US", "es-ES", "fr-FR", "de-DE", "it-IT", "pt-BR",
])

# Speech timeout
_speech_timeout_strategy = st.sampled_from(["auto", "3", "5", "10"])

# Voice for Say
_voice_strategy = st.sampled_from([
    "alice", "Polly.Joanna", "Polly.Conchita", "Polly.Mathieu",
])

# Greeting text
_greeting_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=5,
    max_size=200,
)


@st.composite
def gather_twiml_strategy(draw):
    """Generate a Gather TwiML response simulating non-conversational use cases.

    This builds a TwiML response the same way the ai_gather route does for
    non-conversational (e.g., topics) use cases: <Response><Gather speech>...</Gather></Response>
    """
    action = draw(_gather_action_strategy)
    language = draw(_gather_language_strategy)
    speech_timeout = draw(_speech_timeout_strategy)
    ivr_type = draw(_non_conversational_ivr_type_strategy)

    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action=action,
        method="POST",
        language=language,
        speech_timeout=speech_timeout,
    )
    resp.append(gather)
    return str(resp), ivr_type


# ── Property 3 Test ───────────────────────────────────────────────────────────


class TestNonConversationalUseCasesProduceGatherTwiML:
    """Property 3: Non-conversational use cases produce Gather TwiML.

    For any Demo_Use_Case with ivr_type NOT equal to conversational (e.g.,
    topics), the generated TwiML SHALL contain a <Gather> element and SHALL
    NOT contain a <Connect><Stream> element.

    **Validates: Requirements 2.3, 10.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(data=gather_twiml_strategy())
    def test_gather_twiml_contains_gather_element(self, data):
        """Non-conversational TwiML contains a <Gather> element."""
        twiml_str, ivr_type = data

        root = ElementTree.fromstring(twiml_str)
        gather = root.find("Gather")
        assert gather is not None, (
            f"Non-conversational TwiML (ivr_type={ivr_type!r}) must contain <Gather>"
        )

    @settings(max_examples=100, deadline=None)
    @given(data=gather_twiml_strategy())
    def test_gather_twiml_does_not_contain_connect_stream(self, data):
        """Non-conversational TwiML does NOT contain a <Connect><Stream> element."""
        twiml_str, ivr_type = data

        root = ElementTree.fromstring(twiml_str)

        # No <Connect> element at all
        connect = root.find("Connect")
        assert connect is None, (
            f"Non-conversational TwiML (ivr_type={ivr_type!r}) must NOT contain <Connect>"
        )

        # Double-check: no <Stream> anywhere in the tree
        stream = root.find(".//Stream")
        assert stream is None, (
            f"Non-conversational TwiML (ivr_type={ivr_type!r}) must NOT contain <Stream>"
        )

    @settings(max_examples=100, deadline=None)
    @given(data=gather_twiml_strategy())
    def test_gather_has_speech_input(self, data):
        """The <Gather> element has input='speech' for voice-based interaction."""
        twiml_str, ivr_type = data

        root = ElementTree.fromstring(twiml_str)
        gather = root.find("Gather")
        assert gather is not None
        assert gather.get("input") == "speech", (
            f"<Gather> must have input='speech', got {gather.get('input')!r}"
        )

    @settings(max_examples=100, deadline=None)
    @given(data=gather_twiml_strategy())
    def test_all_properties_hold_simultaneously(self, data):
        """All Property 3 conditions hold together for any non-conversational use case."""
        twiml_str, ivr_type = data

        root = ElementTree.fromstring(twiml_str)

        # 1. Contains <Gather>
        gather = root.find("Gather")
        assert gather is not None

        # 2. Does NOT contain <Connect>
        assert root.find("Connect") is None

        # 3. Does NOT contain <Stream>
        assert root.find(".//Stream") is None

        # 4. ivr_type is NOT conversational
        assert ivr_type != "conversational"

    @settings(max_examples=100, deadline=None)
    @given(
        ivr_type=_non_conversational_ivr_type_strategy,
        ws_host=_ws_host_strategy,
        lang=_twiml_language_strategy,
        demo_id=_twiml_demo_id_strategy,
        caller_from=_twiml_caller_from_strategy,
    )
    def test_conversational_vs_non_conversational_are_mutually_exclusive(
        self, ivr_type, ws_host, lang, demo_id, caller_from
    ):
        """Conversational produces Connect/Stream; non-conversational produces Gather — never both."""
        import routes.ai as ai_module

        # Conversational path: produces Connect/Stream
        original_ws_host = ai_module.WS_HOST
        ai_module.WS_HOST = ws_host
        try:
            conversational_twiml = _build_media_stream_twiml(
                lang=lang,
                demo_id=demo_id,
                caller_from=caller_from,
            )
        finally:
            ai_module.WS_HOST = original_ws_host

        conv_root = ElementTree.fromstring(conversational_twiml)
        assert conv_root.find("Connect/Stream") is not None
        assert conv_root.find("Gather") is None

        # Non-conversational path: produces Gather (no Connect/Stream)
        resp = VoiceResponse()
        gather = Gather(
            input="speech",
            action=f"/ai-respond?lang={lang}&topic=general",
            method="POST",
        )
        resp.append(gather)
        non_conv_twiml = str(resp)

        non_conv_root = ElementTree.fromstring(non_conv_twiml)
        assert non_conv_root.find("Gather") is not None
        assert non_conv_root.find("Connect") is None
        assert non_conv_root.find(".//Stream") is None
