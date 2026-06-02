"""Streaming text-to-speech client using ElevenLabs API.

Converts text chunks from the LLM into mulaw 8kHz audio for Twilio
Media Streams playback. Uses httpx for async streaming HTTP requests
to the ElevenLabs TTS endpoint.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Output format matching Twilio Media Streams requirements (mulaw 8000Hz)
OUTPUT_FORMAT = "ulaw_8000"

# Default model for TTS synthesis (multilingual, more stable prosody)
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# ElevenLabs API base URL
_API_BASE_URL = "https://api.elevenlabs.io/v1"

# Streaming chunk size for reading response
_STREAM_CHUNK_SIZE = 1024


# ---------------------------------------------------------------------------
# ElevenLabsTTSClient
# ---------------------------------------------------------------------------


class ElevenLabsTTSClient:
    """Streaming TTS via ElevenLabs HTTP streaming API.

    Converts text chunks into mulaw 8kHz audio suitable for Twilio Media
    Streams. Each call to synthesize_stream sends text to ElevenLabs and
    forwards audio chunks to the provided callback as they arrive.

    Configuration:
    - Output format: ulaw_8000 (mulaw 8000Hz, matching Twilio)
    - API key: from ELEVENLABS_API_KEY environment variable
    - Default voice: from DEFAULT_ELEVENLABS_VOICE_ID environment variable
    - Model: eleven_flash_v2_5 (optimized for low latency)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = DEFAULT_MODEL_ID,
    ) -> None:
        """Initialize the ElevenLabs TTS client.

        Args:
            api_key: ElevenLabs API key. Defaults to ELEVENLABS_API_KEY env var.
            model_id: The TTS model to use. Defaults to eleven_flash_v2_5.
        """
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not self._api_key:
            try:
                from src.config import SecretsConfig
                self._api_key = SecretsConfig.get("ELEVENLABS_API_KEY", "")
            except Exception:
                pass
        self._model_id = model_id
        self._default_voice_id = os.environ.get("DEFAULT_ELEVENLABS_VOICE_ID", "")
        if not self._default_voice_id:
            try:
                from src.config import SecretsConfig
                self._default_voice_id = SecretsConfig.get("DEFAULT_ELEVENLABS_VOICE_ID", "")
            except Exception:
                pass
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    def _resolve_voice_id(self, voice_id: str | None) -> str:
        """Resolve the voice ID to use, falling back to the default.

        Args:
            voice_id: The requested voice ID (may be None or empty).

        Returns:
            The voice ID to use for synthesis.
        """
        if voice_id:
            return voice_id
        return self._default_voice_id

    async def synthesize_stream(
        self,
        text: str,
        voice_id: str,
        on_audio_chunk: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Synthesize text to speech and stream audio chunks via callback.

        Sends text to ElevenLabs streaming TTS API and forwards each audio
        chunk to the provided callback as it arrives. Output format is mulaw
        8000Hz to match Twilio Media Streams requirements.

        On failure, logs the error and returns without raising — the pipeline
        continues with the next text chunk.

        Args:
            text: The text to synthesize into speech.
            voice_id: The ElevenLabs voice ID to use. Falls back to
                DEFAULT_ELEVENLABS_VOICE_ID env var if empty/None.
            on_audio_chunk: Async callback invoked with each audio chunk
                (raw mulaw bytes) as it arrives from ElevenLabs.
        """
        if not text or not text.strip():
            return

        resolved_voice_id = self._resolve_voice_id(voice_id)
        if not resolved_voice_id:
            logger.error(
                "No voice ID available for TTS synthesis",
                extra={"text_preview": text[:50]},
            )
            return

        url = f"{_API_BASE_URL}/text-to-speech/{resolved_voice_id}/stream"

        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "model_id": self._model_id,
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        params = {
            "output_format": OUTPUT_FORMAT,
        }

        try:
            async with self._http_client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                params=params,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error(
                        "TTS API error response",
                        extra={
                            "status_code": response.status_code,
                            "body_preview": body[:200].decode(errors="replace"),
                            "voice_id": resolved_voice_id,
                        },
                    )
                    return

                async for chunk in response.aiter_bytes(chunk_size=_STREAM_CHUNK_SIZE):
                    if chunk:
                        try:
                            await on_audio_chunk(chunk)
                        except Exception as cb_exc:
                            logger.warning(
                                "TTS audio chunk callback error",
                                extra={
                                    "error": str(cb_exc),
                                    "voice_id": resolved_voice_id,
                                },
                            )

        except Exception as exc:
            logger.error(
                "TTS synthesis error",
                extra={
                    "error": str(exc),
                    "voice_id": resolved_voice_id,
                    "text_preview": text[:80],
                    "model_id": self._model_id,
                },
            )
            # Skip this chunk — don't crash the pipeline

    async def close(self) -> None:
        """Gracefully shut down the TTS client.

        Closes the underlying HTTP client and releases resources.
        """
        logger.info("Closing ElevenLabs TTS client")
        try:
            await self._http_client.aclose()
        except Exception as exc:
            logger.debug(
                "Error closing ElevenLabs HTTP client",
                extra={"error": str(exc)},
            )
        logger.info("ElevenLabs TTS client closed")
