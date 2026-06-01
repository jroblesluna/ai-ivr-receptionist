"""Data models for the real-time voice conversation pipeline.

Defines pipeline state, session state, and Twilio Media Stream message types
used throughout the WebSocket-based audio pipeline.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CONVERSATION_HISTORY = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cap_conversation_history(history: list[dict]) -> list[dict]:
    """Return at most the most recent MAX_CONVERSATION_HISTORY messages.

    If the history contains more than 50 messages, only the last 50 are
    retained, preserving their original order. If 50 or fewer, the list is
    returned unchanged.
    """
    if len(history) > MAX_CONVERSATION_HISTORY:
        return history[-MAX_CONVERSATION_HISTORY:]
    return history


# ---------------------------------------------------------------------------
# Pipeline State
# ---------------------------------------------------------------------------


class PipelineState(Enum):
    """State machine for the audio pipeline lifecycle."""

    LISTENING = "listening"  # Waiting for caller speech
    PROCESSING = "processing"  # STT finalized, LLM generating
    SPEAKING = "speaking"  # TTS audio being sent to Twilio
    INTERRUPTED = "interrupted"  # Barge-in detected, flushing


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------


@dataclass
class SessionState:
    """Per-call state for a real-time voice conversation session."""

    call_sid: str
    stream_sid: str
    language: str
    demo_id: str
    caller_from: str
    voice_id: str
    pipeline_state: PipelineState = PipelineState.LISTENING
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    collected_info: dict[str, Any] = field(default_factory=dict)
    partial_transcript: str = ""
    interrupted_text: str = ""
    turn_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Twilio Media Stream Messages — Inbound
# ---------------------------------------------------------------------------


class TwilioMediaFormat(TypedDict):
    """Media format descriptor from a Twilio start event."""

    encoding: str  # e.g. "audio/x-mulaw"
    sampleRate: int  # e.g. 8000
    channels: int  # e.g. 1


class TwilioCustomParameters(TypedDict, total=False):
    """Custom parameters passed via <Stream> TwiML element."""

    lang: str
    demo_id: str
    caller_from: str


class TwilioStartData(TypedDict):
    """Payload of a Twilio 'start' event."""

    streamSid: str
    accountSid: str
    callSid: str
    customParameters: TwilioCustomParameters
    mediaFormat: TwilioMediaFormat


class TwilioMediaData(TypedDict):
    """Payload of a Twilio 'media' event."""

    track: str  # "inbound" or "outbound"
    chunk: str
    timestamp: str
    payload: str  # base64-encoded mulaw audio


class TwilioConnectedMessage(TypedDict):
    """Twilio 'connected' event message."""

    event: str  # "connected"
    protocol: str  # "Call"
    version: str  # "1.0.0"


class TwilioStartMessage(TypedDict):
    """Twilio 'start' event message."""

    event: str  # "start"
    sequenceNumber: str
    start: TwilioStartData
    streamSid: str


class TwilioMediaMessage(TypedDict):
    """Twilio 'media' event message."""

    event: str  # "media"
    sequenceNumber: str
    media: TwilioMediaData
    streamSid: str


class TwilioStopMessage(TypedDict):
    """Twilio 'stop' event message."""

    event: str  # "stop"
    sequenceNumber: str
    streamSid: str


# ---------------------------------------------------------------------------
# Twilio Media Stream Messages — Outbound (sent by our server)
# ---------------------------------------------------------------------------


class OutboundMediaPayload(TypedDict):
    """Payload field for an outbound media message."""

    payload: str  # base64-encoded mulaw audio


class OutboundMediaMessage(TypedDict):
    """Outbound media message sent to Twilio to play audio to the caller."""

    event: str  # "media"
    streamSid: str
    media: OutboundMediaPayload


class OutboundClearMessage(TypedDict):
    """Outbound clear message sent to Twilio to flush the audio buffer."""

    event: str  # "clear"
    streamSid: str


class OutboundMarkName(TypedDict):
    """Mark name payload for tracking playback position."""

    name: str


class OutboundMarkMessage(TypedDict):
    """Outbound mark message sent to Twilio for playback position tracking."""

    event: str  # "mark"
    streamSid: str
    mark: OutboundMarkName


# ---------------------------------------------------------------------------
# Parsing Helpers
# ---------------------------------------------------------------------------

DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"


def parse_start_event(msg: TwilioStartMessage, voice_id: str = DEFAULT_VOICE_ID) -> SessionState:
    """Extract session parameters from a Twilio 'start' event message.

    Parses the call SID, stream SID, and custom parameters (language, demo_id,
    caller_from) from the start event and returns a new SessionState instance.

    Args:
        msg: A Twilio 'start' event message.
        voice_id: The ElevenLabs voice ID to use for TTS. Defaults to a
            standard voice if not provided.

    Returns:
        A new SessionState populated with the extracted parameters.
    """
    start_data = msg["start"]
    custom_params = start_data["customParameters"]

    return SessionState(
        call_sid=start_data["callSid"],
        stream_sid=start_data["streamSid"],
        language=custom_params.get("lang", "en"),
        demo_id=custom_params.get("demo_id", ""),
        caller_from=custom_params.get("caller_from", ""),
        voice_id=voice_id,
    )


def encode_audio_for_twilio(audio_bytes: bytes, stream_sid: str) -> OutboundMediaMessage:
    """Encode raw audio bytes into an outbound Twilio media message.

    For any raw audio byte sequence, encoding it for Twilio produces a JSON
    message with event set to "media", the correct streamSid, and
    media.payload containing the base64 encoding of the input bytes — such
    that base64.b64decode(output.media.payload) == input_bytes.

    Args:
        audio_bytes: Raw audio bytes (e.g. mulaw 8kHz from TTS).
        stream_sid: The Twilio stream SID to address the message to.

    Returns:
        An OutboundMediaMessage dict ready to be serialized and sent over WebSocket.
    """
    payload_b64 = base64.b64encode(audio_bytes).decode("ascii")
    return OutboundMediaMessage(
        event="media",
        streamSid=stream_sid,
        media=OutboundMediaPayload(payload=payload_b64),
    )


def decode_media_payload(media_msg: TwilioMediaMessage) -> bytes:
    """Decode the base64-encoded audio payload from a Twilio media event.

    For any valid Twilio media event with a base64-encoded mulaw payload,
    decoding the payload produces the exact same bytes that were originally
    encoded by Twilio.

    Args:
        media_msg: A Twilio 'media' event message containing a base64 payload.

    Returns:
        The decoded raw audio bytes.
    """
    return base64.b64decode(media_msg["media"]["payload"])


def process_transcript(
    transcript: str,
    is_final: bool,
    buffer: list[str],
) -> bool:
    """Process a transcript result, buffering interim results and triggering LLM on final.

    For any sequence of STT transcript results, the LLM SHALL be invoked if
    and only if a result has is_final set to true. Interim results (where
    is_final is false) SHALL be buffered without triggering LLM processing.

    Args:
        transcript: The transcribed text from STT.
        is_final: Whether this is a final transcript result.
        buffer: Mutable list used to accumulate interim transcripts.

    Returns:
        True if LLM should be triggered (is_final=True), False otherwise.
    """
    if is_final:
        # Final transcript: clear buffer and signal LLM invocation
        buffer.clear()
        return True
    else:
        # Interim transcript: buffer without triggering LLM
        buffer.append(transcript)
        return False
