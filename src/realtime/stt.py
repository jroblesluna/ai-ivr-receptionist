"""Streaming speech-to-text client using Deepgram WebSocket API.

Uses direct WebSocket connection (via websockets library) for maximum
reliability and SDK-version independence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable

import websockets

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

_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


# ---------------------------------------------------------------------------
# DeepgramSTTClient
# ---------------------------------------------------------------------------


class DeepgramSTTClient:
    """Streaming STT via Deepgram WebSocket API (direct WebSocket).

    Maintains a persistent WebSocket connection to Deepgram's live
    transcription service. Audio bytes are forwarded in real time and
    transcript results (interim and final) are delivered via registered
    callbacks.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        if not api_key:
            try:
                from src.config import SecretsConfig
                api_key = SecretsConfig.get("DEEPGRAM_API_KEY", "")
            except Exception:
                pass
        self._api_key = api_key
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = False
        self._transcript_callbacks: list[Callable[[str, bool], Awaitable[None]]] = []
        self._receive_task: asyncio.Task | None = None

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
        """Open a persistent WebSocket connection to Deepgram."""
        self._encoding = encoding
        self._sample_rate = sample_rate
        self._channels = channels
        await self._establish_connection()

    async def _establish_connection(self) -> None:
        """Create the Deepgram live WebSocket connection."""
        try:
            params = (
                f"?model=nova-2"
                f"&encoding={self._encoding}"
                f"&sample_rate={self._sample_rate}"
                f"&channels={self._channels}"
                f"&interim_results=true"
                f"&endpointing={self._endpointing_ms}"
            )
            url = f"{_DEEPGRAM_WS_URL}{params}"

            self._ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Token {self._api_key}"},
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True

            # Start background task to receive transcripts
            self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info(
                "Deepgram STT connected (direct WebSocket)",
                extra={
                    "encoding": self._encoding,
                    "sample_rate": self._sample_rate,
                    "channels": self._channels,
                },
            )

        except Exception as exc:
            self._connected = False
            logger.error(
                "Failed to connect to Deepgram STT",
                extra={"error": str(exc)},
            )
            raise

    @property
    def _endpointing_ms(self) -> int:
        return DEFAULT_ENDPOINTING_MS

    async def _receive_loop(self) -> None:
        """Background task that receives transcript messages from Deepgram."""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    # Extract transcript from Deepgram response
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        is_final = data.get("is_final", False)

                        if transcript:
                            for callback in self._transcript_callbacks:
                                try:
                                    await callback(transcript, is_final)
                                except Exception as cb_exc:
                                    logger.error(
                                        "Transcript callback error",
                                        extra={"error": str(cb_exc)},
                                    )
                except json.JSONDecodeError:
                    pass
                except Exception as exc:
                    logger.warning(
                        "Error processing Deepgram message",
                        extra={"error": str(exc)},
                    )
        except websockets.ConnectionClosed:
            logger.info("Deepgram WebSocket connection closed")
            self._connected = False
        except Exception as exc:
            logger.error(
                "Deepgram receive loop error",
                extra={"error": str(exc)},
            )
            self._connected = False

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Forward decoded audio bytes to Deepgram for transcription."""
        if not self._connected or self._ws is None:
            raise RuntimeError("STT connection not established. Call connect() first.")

        try:
            await self._ws.send(audio_bytes)
        except Exception as exc:
            logger.warning(
                "Error sending audio to Deepgram",
                extra={"error": str(exc)},
            )
            self._connected = False
            raise

    def on_transcript(self, callback: Callable[[str, bool], Awaitable[None]]) -> None:
        """Register a callback for transcript results."""
        self._transcript_callbacks.append(callback)

    async def reconnect(self) -> bool:
        """Attempt to reconnect with timeout and retry limits."""
        logger.info("Attempting Deepgram STT reconnection")
        await self._close_connection()

        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            try:
                await asyncio.wait_for(
                    self._establish_connection(),
                    timeout=RECONNECT_TIMEOUT_SECONDS,
                )
                logger.info("Deepgram STT reconnected", extra={"attempt": attempt})
                return True
            except asyncio.TimeoutError:
                logger.warning("Deepgram STT reconnection timed out", extra={"attempt": attempt})
            except Exception as exc:
                logger.warning("Deepgram STT reconnection failed", extra={"attempt": attempt, "error": str(exc)})

        logger.error("Deepgram STT reconnection failed after all attempts")
        return False

    async def _close_connection(self) -> None:
        """Close the current WebSocket connection."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass
            self._receive_task = None

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._connected = False

    async def close(self) -> None:
        """Gracefully shut down the STT client."""
        logger.info("Closing Deepgram STT client")
        await self._close_connection()
        self._transcript_callbacks.clear()
        logger.info("Deepgram STT client closed")

    @property
    def is_connected(self) -> bool:
        """Whether the client currently has an active connection."""
        return self._connected
