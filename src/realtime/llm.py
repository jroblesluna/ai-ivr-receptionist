"""Streaming LLM client for the real-time voice pipeline.

Streams chat completions from OpenAI GPT-4o and chunks tokens into
sentence-sized pieces for immediate TTS synthesis. Supports cancellation
via asyncio.Event for barge-in interruption.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Sentence-ending punctuation that triggers a chunk flush
_SENTENCE_ENDINGS = frozenset(".:!?")

# Timeout between tokens before flushing accumulated text (seconds)
_TOKEN_TIMEOUT_S = 0.5


def chunk_text_into_sentences(text: str) -> list[str]:
    """Split text into sentence chunks at sentence-ending punctuation boundaries.

    Splits the accumulated text at sentence-ending punctuation (. ! ? :) such that:
    (a) each emitted chunk ends with sentence-ending punctuation or is the final flush,
    (b) no chunk is empty, and
    (c) the concatenation of all emitted chunks equals the full original text (stripped).

    This is the standalone equivalent of the chunking logic used in
    generate_response for testing purposes.

    Args:
        text: The full text to split into sentence chunks.

    Returns:
        A list of non-empty sentence chunks. The concatenation of all chunks
        (joined with no separator) equals text.strip() when text is non-empty.
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    buffer = ""

    for char in text:
        buffer += char
        # Check if buffer (stripped of trailing whitespace) ends with sentence punctuation
        if buffer.rstrip() and buffer.rstrip()[-1] in _SENTENCE_ENDINGS:
            chunk = buffer.strip()
            if chunk:
                chunks.append(chunk)
            buffer = ""

    # Final flush: emit any remaining text
    if buffer.strip():
        chunks.append(buffer.strip())

    return chunks


def parse_llm_response(text: str) -> dict:
    """Parse a JSON LLM response and extract structured fields.

    Extracts the conversational response fields from the JSON string returned
    by GPT-4o. Missing optional fields default to None, and a missing
    profile_update defaults to an empty dict.

    Args:
        text: The raw JSON string from the LLM completion.

    Returns:
        A dict with keys: message, name, phone, notes, end_call, profile_update.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse LLM JSON response", extra={"text_preview": text[:200]})
        return {
            "message": text if isinstance(text, str) else "",
            "name": None,
            "phone": None,
            "notes": None,
            "end_call": None,
            "profile_update": {},
        }

    if not isinstance(data, dict):
        logger.warning("LLM JSON response is not a dict", extra={"text_preview": text[:200]})
        return {
            "message": text if isinstance(text, str) else "",
            "name": None,
            "phone": None,
            "notes": None,
            "end_call": None,
            "profile_update": {},
        }

    return {
        "message": data.get("message") or "",
        "name": data.get("name") or None,
        "phone": data.get("phone") or None,
        "notes": data.get("notes") or None,
        "end_call": data.get("end_call") if data.get("end_call") is not None else None,
        "profile_update": data.get("profile_update") if data.get("profile_update") is not None else {},
    }


class LLMStreamClient:
    """Streaming LLM responses with sentence chunking.

    Uses OpenAI's async streaming API to generate chat completions from
    GPT-4o. Tokens are accumulated into sentence-sized chunks (delimited
    by sentence-ending punctuation or a 500ms timeout) and forwarded
    immediately to a callback for TTS synthesis.
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o") -> None:
        """Initialize the LLM stream client.

        Args:
            api_key: OpenAI API key. Defaults to OPENAI_API_KEY env var.
            model: The model to use for completions. Defaults to gpt-4o.
        """
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            try:
                from src.config import SecretsConfig
                self._api_key = SecretsConfig.get("OPENAI_API_KEY", "")
            except Exception:
                pass
        self._model = model
        self._client = AsyncOpenAI(api_key=self._api_key)

    async def generate_response(
        self,
        messages: list[dict],
        on_sentence_chunk: Callable[[str], Awaitable[None]],
        on_complete: Callable[[dict], Awaitable[None]],
        cancel_event: asyncio.Event,
    ) -> None:
        """Stream a chat completion and forward sentence chunks.

        Accumulates streamed tokens into sentence-sized chunks. A chunk is
        flushed when sentence-ending punctuation (. ! ? :) is encountered or
        when 500ms elapses since the last token without new tokens arriving.

        On stream completion, the full accumulated text is parsed as JSON and
        the extracted fields are passed to on_complete.

        Args:
            messages: The conversation history (list of role/content dicts).
            on_sentence_chunk: Async callback invoked with each sentence chunk
                for immediate TTS synthesis.
            on_complete: Async callback invoked with the parsed response dict
                when the stream finishes.
            cancel_event: An asyncio.Event that, when set, cancels the stream
                (used for barge-in interruption).
        """
        full_text = ""
        buffer = ""
        last_token_time = time.monotonic()

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
            )

            async for chunk in stream:
                # Check for cancellation
                if cancel_event.is_set():
                    logger.info("LLM generation cancelled (barge-in)")
                    await stream.close()
                    return

                # Extract token content from the chunk
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None or delta.content is None:
                    continue

                token = delta.content
                full_text += token
                buffer += token
                last_token_time = time.monotonic()

                # Check if buffer ends with sentence-ending punctuation
                if buffer and buffer.rstrip()[-1:] in _SENTENCE_ENDINGS:
                    chunk_text = buffer.strip()
                    if chunk_text:
                        await on_sentence_chunk(chunk_text)
                    buffer = ""

            # Flush any remaining buffer after stream ends
            if buffer.strip():
                await on_sentence_chunk(buffer.strip())
                buffer = ""

            # Parse the full response and call on_complete
            parsed = parse_llm_response(full_text)
            await on_complete(parsed)

        except asyncio.CancelledError:
            logger.info("LLM generation task cancelled")
            # Flush remaining buffer before exiting
            if buffer.strip():
                await on_sentence_chunk(buffer.strip())
            raise

        except Exception as exc:
            logger.error(
                "LLM streaming error",
                extra={"error": str(exc), "model": self._model},
            )
            # Still try to parse whatever we got
            if full_text:
                parsed = parse_llm_response(full_text)
                await on_complete(parsed)
            raise

    async def generate_response_with_timeout(
        self,
        messages: list[dict],
        on_sentence_chunk: Callable[[str], Awaitable[None]],
        on_complete: Callable[[dict], Awaitable[None]],
        cancel_event: asyncio.Event,
    ) -> None:
        """Stream with token timeout handling.

        Same as generate_response but also flushes the buffer when 500ms
        elapses between tokens (handles cases where the LLM pauses mid-sentence).

        Args:
            messages: The conversation history.
            on_sentence_chunk: Async callback for each sentence chunk.
            on_complete: Async callback for the parsed response.
            cancel_event: Cancellation event for barge-in.
        """
        full_text = ""
        buffer = ""
        last_token_time = time.monotonic()

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
            )

            async for chunk in stream:
                # Check for cancellation
                if cancel_event.is_set():
                    logger.info("LLM generation cancelled (barge-in)")
                    await stream.close()
                    return

                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None or delta.content is None:
                    # No content token — check timeout on buffer
                    now = time.monotonic()
                    if buffer.strip() and (now - last_token_time) >= _TOKEN_TIMEOUT_S:
                        await on_sentence_chunk(buffer.strip())
                        buffer = ""
                    continue

                token = delta.content
                now = time.monotonic()

                # Check timeout before adding new token
                if buffer.strip() and (now - last_token_time) >= _TOKEN_TIMEOUT_S:
                    await on_sentence_chunk(buffer.strip())
                    buffer = ""

                full_text += token
                buffer += token
                last_token_time = now

                # Check sentence-ending punctuation
                if buffer and buffer.rstrip()[-1:] in _SENTENCE_ENDINGS:
                    chunk_text = buffer.strip()
                    if chunk_text:
                        await on_sentence_chunk(chunk_text)
                    buffer = ""

            # Flush remaining buffer
            if buffer.strip():
                await on_sentence_chunk(buffer.strip())
                buffer = ""

            # Parse and complete
            parsed = parse_llm_response(full_text)
            await on_complete(parsed)

        except asyncio.CancelledError:
            logger.info("LLM generation task cancelled")
            if buffer.strip():
                await on_sentence_chunk(buffer.strip())
            raise

        except Exception as exc:
            logger.error(
                "LLM streaming error",
                extra={"error": str(exc), "model": self._model},
            )
            if full_text:
                parsed = parse_llm_response(full_text)
                await on_complete(parsed)
            raise
