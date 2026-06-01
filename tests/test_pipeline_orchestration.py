"""Unit tests for the audio pipeline orchestration logic in server.py (task 9.2).

Tests the pipeline wiring: STT → LLM → TTS → Twilio, state machine transitions,
barge-in handling, and opening greeting generation.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.realtime.models import PipelineState, SessionState
from src.realtime.session import ConversationSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    call_sid: str = "CA_test",
    stream_sid: str = "MZ_test",
    language: str = "en",
    demo_id: str = "demo_test",
    caller_from: str = "+15551234567",
    voice_id: str = "voice_test",
) -> ConversationSession:
    """Create a ConversationSession with mocked pipeline components."""
    session = ConversationSession(
        call_sid=call_sid,
        stream_sid=stream_sid,
        language=language,
        demo_id=demo_id,
        caller_from=caller_from,
        voice_id=voice_id,
    )
    # Don't call initialize() — set up mocks manually
    session.stt_client = AsyncMock()
    session.tts_client = AsyncMock()
    session.vad_processor = MagicMock()
    session.playback_tracker = MagicMock()
    session.playback_tracker.get_partial_text_at_interruption.return_value = ""
    return session


# ---------------------------------------------------------------------------
# State Machine Transition Tests
# ---------------------------------------------------------------------------


class TestStateMachineTransitions:
    """Tests for pipeline state machine transitions."""

    @pytest.mark.asyncio
    async def test_initial_state_is_listening(self):
        """New session starts in LISTENING state."""
        session = _make_session()
        assert session.pipeline_state == PipelineState.LISTENING

    @pytest.mark.asyncio
    async def test_on_final_transcript_transitions_to_processing(self):
        """Receiving a final transcript transitions from LISTENING to PROCESSING."""
        from src.realtime.server import _on_transcript

        session = _make_session()
        ws = AsyncMock()

        with patch("src.realtime.server._generate_and_speak", new_callable=AsyncMock) as mock_gen:
            # Make the task complete immediately
            mock_gen.return_value = None

            await _on_transcript(session, ws, "Hello there", is_final=True)

            assert session.pipeline_state == PipelineState.PROCESSING

    @pytest.mark.asyncio
    async def test_interim_transcript_does_not_change_state(self):
        """Interim transcripts do not change pipeline state."""
        from src.realtime.server import _on_transcript

        session = _make_session()
        ws = AsyncMock()

        await _on_transcript(session, ws, "Hel", is_final=False)

        assert session.pipeline_state == PipelineState.LISTENING
        assert session.state.partial_transcript == "Hel"

    @pytest.mark.asyncio
    async def test_barge_in_transitions_speaking_to_listening(self):
        """Barge-in during SPEAKING transitions to LISTENING."""
        from src.realtime.server import _handle_barge_in

        session = _make_session()
        session.pipeline_state = PipelineState.SPEAKING
        ws = AsyncMock()

        await _handle_barge_in(session, ws)

        assert session.pipeline_state == PipelineState.LISTENING


# ---------------------------------------------------------------------------
# Barge-In Handling Tests
# ---------------------------------------------------------------------------


class TestBargeInHandling:
    """Tests for barge-in (interruption) handling."""

    @pytest.mark.asyncio
    async def test_barge_in_sends_clear_message(self):
        """Barge-in sends a clear message to Twilio."""
        from src.realtime.server import _handle_barge_in

        session = _make_session()
        session.pipeline_state = PipelineState.SPEAKING
        ws = AsyncMock()

        await _handle_barge_in(session, ws)

        # Verify clear message was sent
        ws.send_json.assert_awaited_once()
        clear_msg = ws.send_json.call_args[0][0]
        assert clear_msg["event"] == "clear"
        assert clear_msg["streamSid"] == "MZ_test"

    @pytest.mark.asyncio
    async def test_barge_in_saves_partial_text(self):
        """Barge-in saves partial response text to conversation history."""
        from src.realtime.server import _handle_barge_in

        session = _make_session()
        session.pipeline_state = PipelineState.SPEAKING
        session.playback_tracker.get_partial_text_at_interruption.return_value = "Hello, how can I"
        ws = AsyncMock()

        await _handle_barge_in(session, ws)

        # Verify partial text saved to history with interrupted marker
        history = session.state.conversation_history
        assert len(history) == 1
        assert history[0]["role"] == "assistant"
        assert history[0]["content"] == "Hello, how can I"
        assert history[0]["interrupted"] is True

    @pytest.mark.asyncio
    async def test_barge_in_cancels_generation_task(self):
        """Barge-in cancels the current LLM generation task."""
        from src.realtime.server import _handle_barge_in

        session = _make_session()
        session.pipeline_state = PipelineState.SPEAKING

        # Create a mock task that's not done — use MagicMock so .done() returns a bool
        mock_task = MagicMock()
        mock_task.done.return_value = False
        session.current_generation_task = mock_task

        ws = AsyncMock()

        await _handle_barge_in(session, ws)

        # Verify task was cancelled
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_barge_in_resets_vad(self):
        """Barge-in resets the VAD processor for the next turn."""
        from src.realtime.server import _handle_barge_in

        session = _make_session()
        session.pipeline_state = PipelineState.SPEAKING
        ws = AsyncMock()

        await _handle_barge_in(session, ws)

        session.vad_processor.reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_barge_in_no_partial_text_no_history_entry(self):
        """Barge-in with no partial text does not add to history."""
        from src.realtime.server import _handle_barge_in

        session = _make_session()
        session.pipeline_state = PipelineState.SPEAKING
        session.playback_tracker.get_partial_text_at_interruption.return_value = ""
        ws = AsyncMock()

        await _handle_barge_in(session, ws)

        assert len(session.state.conversation_history) == 0


# ---------------------------------------------------------------------------
# VAD Integration in Media Event Tests
# ---------------------------------------------------------------------------


class TestVADMediaIntegration:
    """Tests for VAD processing within media event handling."""

    @pytest.mark.asyncio
    async def test_speech_start_during_speaking_triggers_barge_in(self):
        """VAD speech_start during SPEAKING state triggers barge-in."""
        from src.realtime.server import _handle_media_event
        from src.realtime.vad import VADEvent

        session = _make_session()
        session.pipeline_state = PipelineState.SPEAKING
        session.vad_processor.process_frame.return_value = VADEvent.SPEECH_START
        ws = AsyncMock()

        msg = {
            "event": "media",
            "media": {
                "track": "inbound",
                "chunk": "1",
                "timestamp": "10",
                "payload": "AAEC",  # base64 of b'\x00\x01\x02'
            },
            "streamSid": "MZ_test",
        }

        await _handle_media_event(msg, session, ws)

        # Verify clear message was sent (barge-in occurred)
        ws.send_json.assert_awaited_once()
        clear_msg = ws.send_json.call_args[0][0]
        assert clear_msg["event"] == "clear"

    @pytest.mark.asyncio
    async def test_speech_start_during_listening_no_barge_in(self):
        """VAD speech_start during LISTENING state does NOT trigger barge-in."""
        from src.realtime.server import _handle_media_event
        from src.realtime.vad import VADEvent

        session = _make_session()
        session.pipeline_state = PipelineState.LISTENING
        session.vad_processor.process_frame.return_value = VADEvent.SPEECH_START
        ws = AsyncMock()

        msg = {
            "event": "media",
            "media": {
                "track": "inbound",
                "chunk": "1",
                "timestamp": "10",
                "payload": "AAEC",
            },
            "streamSid": "MZ_test",
        }

        await _handle_media_event(msg, session, ws)

        # No clear message should be sent
        ws.send_json.assert_not_awaited()


# ---------------------------------------------------------------------------
# Opening Greeting Tests
# ---------------------------------------------------------------------------


class TestOpeningGreeting:
    """Tests for the opening greeting generation."""

    @pytest.mark.asyncio
    async def test_greeting_adds_start_conversation_to_history(self):
        """Opening greeting adds '(start conversation)' user message to history."""
        from src.realtime.server import _trigger_opening_greeting

        session = _make_session()
        ws = AsyncMock()

        with patch("src.realtime.server.LLMStreamClient") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm

            # Make generate_response call on_complete with a parsed response
            async def fake_generate(messages, on_sentence_chunk, on_complete, cancel_event):
                await on_sentence_chunk("Hello! How can I help you today?")
                await on_complete({"message": "Hello! How can I help you today?", "name": None, "phone": None, "notes": None, "end_call": None, "profile_update": {}})

            mock_llm.generate_response = fake_generate

            await _trigger_opening_greeting(session, ws)

        # Verify "(start conversation)" was added as user message
        assert session.state.conversation_history[0] == {
            "role": "user",
            "content": "(start conversation)",
        }

    @pytest.mark.asyncio
    async def test_greeting_transitions_to_processing_then_listening(self):
        """Opening greeting transitions LISTENING → PROCESSING → SPEAKING → LISTENING."""
        from src.realtime.server import _trigger_opening_greeting

        session = _make_session()
        ws = AsyncMock()

        states_seen = []

        # Track state transitions
        original_setter = ConversationSession.pipeline_state.fset

        def tracking_setter(self, value):
            states_seen.append(value)
            original_setter(self, value)

        with patch("src.realtime.server.LLMStreamClient") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm

            async def fake_generate(messages, on_sentence_chunk, on_complete, cancel_event):
                await on_sentence_chunk("Hello!")
                await on_complete({"message": "Hello!", "name": None, "phone": None, "notes": None, "end_call": None, "profile_update": {}})

            mock_llm.generate_response = fake_generate

            with patch.object(ConversationSession, "pipeline_state", new_callable=lambda: property(
                ConversationSession.pipeline_state.fget,
                tracking_setter,
            )):
                await _trigger_opening_greeting(session, ws)

        # Should have transitioned through PROCESSING → SPEAKING → LISTENING
        assert PipelineState.PROCESSING in states_seen
        assert PipelineState.SPEAKING in states_seen
        assert PipelineState.LISTENING in states_seen

    @pytest.mark.asyncio
    async def test_greeting_streams_audio_to_twilio(self):
        """Opening greeting synthesizes TTS and sends audio to Twilio."""
        from src.realtime.server import _trigger_opening_greeting

        session = _make_session()
        ws = AsyncMock()

        # Make TTS call the on_audio_chunk callback
        async def fake_synthesize(text, voice_id, on_audio_chunk):
            await on_audio_chunk(b"\x80\x81\x82")

        session.tts_client.synthesize_stream = fake_synthesize

        with patch("src.realtime.server.LLMStreamClient") as mock_llm_cls:
            mock_llm = AsyncMock()
            mock_llm_cls.return_value = mock_llm

            async def fake_generate(messages, on_sentence_chunk, on_complete, cancel_event):
                await on_sentence_chunk("Hello!")
                await on_complete({"message": "Hello!", "name": None, "phone": None, "notes": None, "end_call": None, "profile_update": {}})

            mock_llm.generate_response = fake_generate

            await _trigger_opening_greeting(session, ws)

        # Verify audio was sent to Twilio
        ws.send_json.assert_awaited()
        sent_msg = ws.send_json.call_args[0][0]
        assert sent_msg["event"] == "media"
        assert sent_msg["streamSid"] == "MZ_test"
        assert "payload" in sent_msg["media"]


# ---------------------------------------------------------------------------
# STT → LLM Pipeline Tests
# ---------------------------------------------------------------------------


class TestSTTToLLMPipeline:
    """Tests for the STT final transcript → LLM generation pipeline."""

    @pytest.mark.asyncio
    async def test_final_transcript_adds_user_message_to_history(self):
        """Final transcript adds user message to conversation history."""
        from src.realtime.server import _on_transcript

        session = _make_session()
        ws = AsyncMock()

        with patch("src.realtime.server._generate_and_speak", new_callable=AsyncMock):
            await _on_transcript(session, ws, "What time is it?", is_final=True)

        assert {"role": "user", "content": "What time is it?"} in session.state.conversation_history

    @pytest.mark.asyncio
    async def test_final_transcript_clears_partial_transcript(self):
        """Final transcript clears the partial transcript buffer."""
        from src.realtime.server import _on_transcript

        session = _make_session()
        session.state.partial_transcript = "What time"
        ws = AsyncMock()

        with patch("src.realtime.server._generate_and_speak", new_callable=AsyncMock):
            await _on_transcript(session, ws, "What time is it?", is_final=True)

        assert session.state.partial_transcript == ""

    @pytest.mark.asyncio
    async def test_empty_transcript_is_ignored(self):
        """Empty or whitespace-only transcripts are ignored."""
        from src.realtime.server import _on_transcript

        session = _make_session()
        ws = AsyncMock()

        await _on_transcript(session, ws, "", is_final=True)
        await _on_transcript(session, ws, "   ", is_final=True)

        assert len(session.state.conversation_history) == 0
        assert session.pipeline_state == PipelineState.LISTENING


# ---------------------------------------------------------------------------
# Send Audio to Twilio Tests
# ---------------------------------------------------------------------------


class TestSendAudioToTwilio:
    """Tests for the _send_audio_to_twilio helper."""

    @pytest.mark.asyncio
    async def test_encodes_and_sends_audio(self):
        """Audio is base64-encoded and sent as a Twilio media message."""
        from src.realtime.server import _send_audio_to_twilio

        session = _make_session()
        ws = AsyncMock()

        await _send_audio_to_twilio(session, ws, b"\x00\x01\x02\x03", "Hello")

        ws.send_json.assert_awaited_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["event"] == "media"
        assert msg["streamSid"] == "MZ_test"

        # Verify payload decodes back to original bytes
        import base64
        decoded = base64.b64decode(msg["media"]["payload"])
        assert decoded == b"\x00\x01\x02\x03"

    @pytest.mark.asyncio
    async def test_records_chunk_in_playback_tracker(self):
        """Sent audio is recorded in the playback tracker."""
        from src.realtime.server import _send_audio_to_twilio

        session = _make_session()
        ws = AsyncMock()

        await _send_audio_to_twilio(session, ws, b"\x80\x81", "Hi there")

        session.playback_tracker.record_chunk_sent.assert_called_once()
        call_args = session.playback_tracker.record_chunk_sent.call_args[0]
        assert call_args[1] == "Hi there"  # text_segment
