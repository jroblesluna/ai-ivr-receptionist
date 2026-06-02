"""Streaming speech-to-text client using Deepgram WebSocket API.

Maintains a persistent WebSocket connection to Deepgram for real-time
transcription of mulaw 8kHz audio from Twilio Media Streams.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RECONNECT_TIMEOUT_SECONDS = 2.0
MAX_RECONNECT_ATTEMPTS = 2
DEFAULT_ENCODING = "mulaw"
DEFAULT_SAMPLE_RATE = 8000
DEFAULT_CHANNELS = 1
DEFAULT_ENDPOINTING_MS = 300


# ---------------------------------------------------------------------------
# DeepgramSTTClient
# ---------------------------------------------------------------------------


class DeepgramSTTClient:
    """Streaming STT via Deepgram WebSocket API.

    Maintains a persistent WebSocket connection to Deepgram's live
    transcription service. Audio bytes are forwarded in real time and
    transcript results (interim and final) are delivered via registered
    callbacks.

    Configuration defaults match Twilio Media Streams format:
    - encoding: mulaw
    - sample_rate: 8000 Hz
    - channels: 1
    - interim_results: true
    - endpointing: 300ms
    """

    def __init__(self) -> None:
        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            try:
                from src.config import SecretsConfig
                api_key = SecretsConfig.get("DEEPGRAM_API_KEY", "")
            except Exception:
                pass
        self._client = AsyncDeepgramClient(api_key=api_key)
        self._connection: object | None = None
        self._connected = False
        self._transcript_callbacks: list[Callable[[str, bool], Awaitable[None]]] = []
        self._listen_task: asyncio.Task | None = None

        # Store connection params for reconnection
        self._encoding: str = DEFAULT_ENCODING
        self._sample_rate: int = DEFAULT_SAMPLE_RATE
        self._channels: int = DEFAULT_CHANNELS

    async def connect(
        self,
        encoding: str = DEFAULT_ENCODING,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
    ) -> None:
        """Open a persistent WebSocket connection to Deepgram.

        Args:
            encoding: Audio encoding format (default: mulaw).
            sample_rate: Audio sample rate in Hz (default: 8000).
            channels: Number of audio channels (default: 1).
        """
        self._encoding = encoding
        self._sample_rate = sample_rate
        self._channels = channels

        await self._establish_connection()

    async def _establish_connection(self) -> None:
        """Create and configure the Deepgram live connection."""
        try:
            self._connection = await self._client.listen.v1.connect(
                model="nova-3",
                encoding=self._encoding,
                sample_rate=self._sample_rate,
                channels=self._channels,
                interim_results=True,
                endpointing=DEFAULT_ENDPOINTING_MS,
            ).__aenter__()

            # Register event handlers
            self._connection.on(EventType.MESSAGE, self._handle_message)
            self._connection.on(EventType.ERROR, self._handle_error)
            self._connection.on(EventType.CLOSE, self._handle_close)

            # Start listening for responses
            await self._connection.start_listening()
            self._connected = True

            logger.info(
                "Deepgram STT connected",
                extra={
                    "encoding": self._encoding,
                    "sample_rate": self._sample_rate,
                    "channels": self._channels,
                    "endpointing_ms": DEFAULT_ENDPOINTING_MS,
                },
            )

        except Exception as exc:
            self._connected = False
            logger.error(
                "Failed to connect to Deepgram STT",
                extra={"error": str(exc)},
            )
            raise

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Forward decoded audio bytes to Deepgram for transcription.

        Args:
            audio_bytes: Raw audio bytes (mulaw encoded) to transcribe.

        Raises:
            RuntimeError: If the connection is not established.
        """
        if not self._connected or self._connection is None:
            raise RuntimeError("STT connection not established. Call connect() first.")

        try:
            await self._connection.send(audio_bytes)
        except Exception as exc:
            logger.warning(
                "Error sending audio to Deepgram",
                extra={"error": str(exc)},
            )
            self._connected = False
            raise

    def on_transcript(self, callback: Callable[[str, bool], Awaitable[None]]) -> None:
        """Register a callback for transcript results.

        The callback receives two arguments:
        - transcript (str): The transcribed text.
        - is_final (bool): True if this is a final transcript, False for interim.

        Args:
            callback: Async callable invoked with (transcript, is_final).
        """
        self._transcript_callbacks.append(callback)

    async def _handle_message(self, message: object) -> None:
        """Process incoming transcript messages from Deepgram.

        Extracts the transcript text and is_final flag, then invokes
        all registered callbacks.
        """
        try:
            # The SDK message object has a .type field and transcript data
            # accessible via attributes or dict-like access depending on version
            transcript = ""
            is_final = False

            if hasattr(message, "channel"):
                # Standard response structure
                channel = message.channel
                if hasattr(channel, "alternatives") and channel.alternatives:
                    alt = channel.alternatives[0]
                    transcript = getattr(alt, "transcript", "")

                is_final = getattr(message, "is_final", False)
            elif isinstance(message, dict):
                # Dict-based response
                channel = message.get("channel", {})
                alternatives = channel.get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")
                is_final = message.get("is_final", False)

            # Only invoke callbacks if there's actual transcript content
            if transcript:
                for callback in self._transcript_callbacks:
                    try:
                        await callback(transcript, is_final)
                    except Exception as cb_exc:
                        logger.error(
                            "Transcript callback error",
                            extra={"error": str(cb_exc)},
                        )

        except Exception as exc:
            logger.error(
                "Error processing Deepgram message",
                extra={"error": str(exc)},
            )

    async def _handle_error(self, error: object) -> None:
        """Handle Deepgram WebSocket errors."""
        logger.error(
            "Deepgram STT error",
            extra={"error": str(error)},
        )

    async def _handle_close(self, close_event: object) -> None:
        """Handle Deepgram WebSocket close events."""
        self._connected = False
        logger.info(
            "Deepgram STT connection closed",
            extra={"event": str(close_event)},
        )

    async def reconnect(self) -> bool:
        """Attempt to reconnect to Deepgram with timeout and retry limits.

        Tries up to MAX_RECONNECT_ATTEMPTS (2) times with a
        RECONNECT_TIMEOUT_SECONDS (2s) timeout per attempt.

        Returns:
            True if reconnection succeeded, False otherwise.
        """
        logger.info("Attempting Deepgram STT reconnection")

        # Close existing connection if any
        await self._close_connection()

        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            try:
                await asyncio.wait_for(
                    self._establish_connection(),
                    timeout=RECONNECT_TIMEOUT_SECONDS,
                )
                logger.info(
                    "Deepgram STT reconnected",
                    extra={"attempt": attempt},
                )
                return True

            except asyncio.TimeoutError:
                logger.warning(
                    "Deepgram STT reconnection timed out",
                    extra={
                        "attempt": attempt,
                        "timeout_seconds": RECONNECT_TIMEOUT_SECONDS,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Deepgram STT reconnection failed",
                    extra={
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )

        logger.error(
            "Deepgram STT reconnection failed after all attempts",
            extra={"max_attempts": MAX_RECONNECT_ATTEMPTS},
        )
        return False

    async def _close_connection(self) -> None:
        """Close the current WebSocket connection if open."""
        if self._connection is not None:
            try:
                await self._connection.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug(
                    "Error during connection close",
                    extra={"error": str(exc)},
                )
            self._connection = None
        self._connected = False

    async def close(self) -> None:
        """Gracefully shut down the STT client.

        Closes the WebSocket connection and cleans up resources.
        """
        logger.info("Closing Deepgram STT client")

        # Cancel listen task if running
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
            self._listen_task = None

        await self._close_connection()
        self._transcript_callbacks.clear()

        logger.info("Deepgram STT client closed")

    @property
    def is_connected(self) -> bool:
        """Whether the client currently has an active connection."""
        return self._connected
