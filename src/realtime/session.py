"""Conversation session management for the real-time voice pipeline.

Provides the ConversationSession class that holds per-call state and manages
the lifecycle of pipeline components (STT, TTS, VAD, playback tracker).
Also provides a module-level session registry for concurrent call management.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.realtime.models import PipelineState, SessionState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level session registry: maps stream_sid → ConversationSession
# ---------------------------------------------------------------------------

_session_registry: dict[str, "ConversationSession"] = {}


def get_session(stream_sid: str) -> Optional["ConversationSession"]:
    """Retrieve an active session by stream SID."""
    return _session_registry.get(stream_sid)


def register_session(stream_sid: str, session: "ConversationSession") -> None:
    """Register a session in the global registry."""
    _session_registry[stream_sid] = session
    logger.info("Session registered", extra={"stream_sid": stream_sid})


def unregister_session(stream_sid: str) -> Optional["ConversationSession"]:
    """Remove a session from the registry and return it (or None)."""
    session = _session_registry.pop(stream_sid, None)
    if session:
        logger.info("Session unregistered", extra={"stream_sid": stream_sid})
    return session


def get_all_sessions() -> dict[str, "ConversationSession"]:
    """Return a copy of the current session registry (for monitoring)."""
    return dict(_session_registry)


# ---------------------------------------------------------------------------
# ConversationSession
# ---------------------------------------------------------------------------


@dataclass
class ConversationSession:
    """Per-call state and pipeline lifecycle manager.

    Holds references to all pipeline components (STT, TTS, VAD, playback
    tracker) and asyncio tasks for a single real-time voice call.
    """

    # Core identifiers
    call_sid: str
    stream_sid: str
    language: str
    demo_id: str
    caller_from: str
    voice_id: str = ""

    # Pipeline state
    state: SessionState = field(init=False)

    # Pipeline component references (Optional since they're set up in initialize())
    # These use string type annotations to avoid import errors before the
    # actual implementation classes exist.
    stt_client: Optional[Any] = None  # DeepgramSTTClient
    tts_client: Optional[Any] = None  # ElevenLabsTTSClient
    vad_processor: Optional[Any] = None  # VADProcessor
    playback_tracker: Optional[Any] = None  # PlaybackTracker

    # Asyncio tasks for pipeline operations
    current_generation_task: Optional[asyncio.Task] = None
    _pipeline_tasks: list[asyncio.Task] = field(default_factory=list)

    # Timestamps
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Initialize the session state after dataclass creation."""
        self.state = SessionState(
            call_sid=self.call_sid,
            stream_sid=self.stream_sid,
            language=self.language,
            demo_id=self.demo_id,
            caller_from=self.caller_from,
            voice_id=self.voice_id,
        )

    @property
    def pipeline_state(self) -> PipelineState:
        """Current pipeline state shortcut."""
        return self.state.pipeline_state

    @pipeline_state.setter
    def pipeline_state(self, value: PipelineState) -> None:
        """Update pipeline state and record activity timestamp."""
        self.state.pipeline_state = value
        self.last_activity_at = time.time()
        self.state.last_activity_at = self.last_activity_at

    @property
    def conversation_history(self) -> list[dict[str, Any]]:
        """Shortcut to session state conversation history."""
        return self.state.conversation_history

    @property
    def collected_info(self) -> dict[str, Any]:
        """Shortcut to session state collected info."""
        return self.state.collected_info

    async def initialize(self) -> None:
        """Set up all pipeline components for this session.

        Creates and connects STT client, TTS client, VAD processor,
        and playback tracker. Components that don't exist yet will be
        initialized when their modules are implemented.
        """
        logger.info(
            "Initializing session pipeline",
            extra={
                "call_sid": self.call_sid,
                "stream_sid": self.stream_sid,
                "demo_id": self.demo_id,
                "language": self.language,
            },
        )

        try:
            # Initialize VAD processor
            # VADProcessor will be imported and created when vad.py is implemented
            try:
                from src.realtime.vad import VADProcessor

                self.vad_processor = VADProcessor()
                logger.debug("VAD processor initialized", extra={"stream_sid": self.stream_sid})
            except ImportError:
                logger.warning("VADProcessor not yet available", extra={"stream_sid": self.stream_sid})

            # Initialize playback tracker
            try:
                from src.realtime.playback import PlaybackTracker

                self.playback_tracker = PlaybackTracker()
                logger.debug("Playback tracker initialized", extra={"stream_sid": self.stream_sid})
            except ImportError:
                logger.warning("PlaybackTracker not yet available", extra={"stream_sid": self.stream_sid})

            # Initialize STT client
            try:
                from src.realtime.stt import DeepgramSTTClient

                self.stt_client = DeepgramSTTClient()
                await self.stt_client.connect(
                    encoding="mulaw",
                    sample_rate=8000,
                    channels=1,
                )
                logger.debug("STT client connected", extra={"stream_sid": self.stream_sid})
            except ImportError:
                logger.warning("DeepgramSTTClient not yet available", extra={"stream_sid": self.stream_sid})

            # Initialize TTS client
            try:
                from src.realtime.tts import ElevenLabsTTSClient

                self.tts_client = ElevenLabsTTSClient()
                logger.debug("TTS client initialized", extra={"stream_sid": self.stream_sid})
            except ImportError:
                logger.warning("ElevenLabsTTSClient not yet available", extra={"stream_sid": self.stream_sid})

            # Register this session in the global registry
            register_session(self.stream_sid, self)

            logger.info(
                "Session pipeline initialized",
                extra={
                    "call_sid": self.call_sid,
                    "stream_sid": self.stream_sid,
                    "stt_ready": self.stt_client is not None,
                    "tts_ready": self.tts_client is not None,
                    "vad_ready": self.vad_processor is not None,
                },
            )

        except Exception as exc:
            logger.error(
                "Failed to initialize session pipeline",
                extra={
                    "call_sid": self.call_sid,
                    "stream_sid": self.stream_sid,
                    "error": str(exc),
                },
            )
            # Clean up any partially initialized components
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        """Close all connections and cancel pending tasks.

        Performs graceful shutdown of all pipeline components:
        1. Cancel the current generation task (LLM/TTS pipeline)
        2. Cancel all tracked pipeline tasks
        3. Close STT connection
        4. Close TTS connection
        5. Reset VAD state
        6. Clear playback tracker
        7. Unregister from the session registry
        """
        logger.info(
            "Cleaning up session",
            extra={
                "call_sid": self.call_sid,
                "stream_sid": self.stream_sid,
                "pipeline_state": self.pipeline_state.value,
            },
        )

        # Cancel current generation task
        if self.current_generation_task and not self.current_generation_task.done():
            self.current_generation_task.cancel()
            try:
                await self.current_generation_task
            except (asyncio.CancelledError, Exception):
                pass
            self.current_generation_task = None

        # Cancel all tracked pipeline tasks
        for task in self._pipeline_tasks:
            if not task.done():
                task.cancel()
        if self._pipeline_tasks:
            await asyncio.gather(*self._pipeline_tasks, return_exceptions=True)
        self._pipeline_tasks.clear()

        # Close STT connection
        if self.stt_client is not None:
            try:
                await self.stt_client.close()
            except Exception as exc:
                logger.warning(
                    "Error closing STT client",
                    extra={"stream_sid": self.stream_sid, "error": str(exc)},
                )
            self.stt_client = None

        # Close TTS connection
        if self.tts_client is not None:
            try:
                await self.tts_client.close()
            except Exception as exc:
                logger.warning(
                    "Error closing TTS client",
                    extra={"stream_sid": self.stream_sid, "error": str(exc)},
                )
            self.tts_client = None

        # Reset VAD processor
        if self.vad_processor is not None:
            try:
                self.vad_processor.reset()
            except Exception as exc:
                logger.warning(
                    "Error resetting VAD processor",
                    extra={"stream_sid": self.stream_sid, "error": str(exc)},
                )
            self.vad_processor = None

        # Clear playback tracker
        if self.playback_tracker is not None:
            try:
                self.playback_tracker.clear()
            except Exception as exc:
                logger.warning(
                    "Error clearing playback tracker",
                    extra={"stream_sid": self.stream_sid, "error": str(exc)},
                )
            self.playback_tracker = None

        # Unregister from session registry
        unregister_session(self.stream_sid)

        logger.info(
            "Session cleanup complete",
            extra={"call_sid": self.call_sid, "stream_sid": self.stream_sid},
        )

    def add_pipeline_task(self, task: asyncio.Task) -> None:
        """Track a pipeline task for cleanup on session end."""
        self._pipeline_tasks.append(task)
        # Remove completed tasks to avoid unbounded growth
        self._pipeline_tasks = [t for t in self._pipeline_tasks if not t.done()]

    def cancel_generation(self) -> None:
        """Cancel the current LLM generation task (used for barge-in)."""
        if self.current_generation_task and not self.current_generation_task.done():
            self.current_generation_task.cancel()
            logger.debug(
                "Generation task cancelled",
                extra={"stream_sid": self.stream_sid},
            )

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity_at = time.time()
        self.state.last_activity_at = self.last_activity_at


# ---------------------------------------------------------------------------
# Barge-in handling
# ---------------------------------------------------------------------------


def handle_barge_in(session: ConversationSession, stream_sid: str) -> "OutboundClearMessage":
    """Handle a barge-in event for a session in SPEAKING state.

    Performs the following actions:
    1. Transitions pipeline_state to INTERRUPTED
    2. Clears the playback tracker
    3. Cancels the current_generation_task (if any)
    4. Returns an OutboundClearMessage to flush Twilio's audio buffer

    Args:
        session: The ConversationSession currently in SPEAKING state.
        stream_sid: The Twilio stream SID for the clear message.

    Returns:
        An OutboundClearMessage dict ready to be sent to Twilio.
    """
    from src.realtime.models import OutboundClearMessage

    # 1. Transition to INTERRUPTED state
    session.pipeline_state = PipelineState.INTERRUPTED

    # 2. Clear the playback tracker
    if session.playback_tracker is not None:
        session.playback_tracker.clear()

    # 3. Cancel the current generation task
    session.cancel_generation()

    # 4. Return a clear message for Twilio
    clear_msg: OutboundClearMessage = {
        "event": "clear",
        "streamSid": stream_sid,
    }
    return clear_msg
