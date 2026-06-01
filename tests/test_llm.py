"""Unit tests for src/realtime/llm.py — LLMStreamClient and parse_llm_response.

Tests the sentence chunking algorithm and JSON response parsing without
requiring a real OpenAI API key (uses mocks for the streaming client).
"""

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.realtime.llm import parse_llm_response, LLMStreamClient, _SENTENCE_ENDINGS


# ── Tests for parse_llm_response ──────────────────────────────────────────────


class TestParseLLMResponse:
    """Unit tests for the parse_llm_response function."""

    def test_full_valid_json(self):
        """All fields present and non-null are extracted correctly."""
        text = json.dumps({
            "message": "Hello, how can I help?",
            "name": "John",
            "phone": "+14085551234",
            "notes": "Interested in product X",
            "end_call": False,
            "profile_update": {"visits": [{"date": "2024-01-01"}]},
        })
        result = parse_llm_response(text)
        assert result["message"] == "Hello, how can I help?"
        assert result["name"] == "John"
        assert result["phone"] == "+14085551234"
        assert result["notes"] == "Interested in product X"
        assert result["end_call"] is False
        assert result["profile_update"] == {"visits": [{"date": "2024-01-01"}]}

    def test_missing_optional_fields_default_to_none(self):
        """Missing optional fields default to None."""
        text = json.dumps({"message": "Hi there!"})
        result = parse_llm_response(text)
        assert result["message"] == "Hi there!"
        assert result["name"] is None
        assert result["phone"] is None
        assert result["notes"] is None
        assert result["end_call"] is None
        assert result["profile_update"] == {}

    def test_null_fields_map_to_none(self):
        """Explicit null values in JSON map to Python None."""
        text = json.dumps({
            "message": "Goodbye!",
            "name": None,
            "phone": None,
            "notes": None,
            "end_call": True,
            "profile_update": None,
        })
        result = parse_llm_response(text)
        assert result["message"] == "Goodbye!"
        assert result["name"] is None
        assert result["phone"] is None
        assert result["notes"] is None
        assert result["end_call"] is True
        assert result["profile_update"] == {}

    def test_empty_string_fields_treated_as_none(self):
        """Empty string values for name/phone/notes are treated as None."""
        text = json.dumps({
            "message": "Hello",
            "name": "",
            "phone": "",
            "notes": "",
        })
        result = parse_llm_response(text)
        assert result["name"] is None
        assert result["phone"] is None
        assert result["notes"] is None

    def test_invalid_json_returns_text_as_message(self):
        """Invalid JSON returns the raw text as the message field."""
        text = "This is not valid JSON"
        result = parse_llm_response(text)
        assert result["message"] == text
        assert result["name"] is None
        assert result["phone"] is None
        assert result["notes"] is None
        assert result["end_call"] is None
        assert result["profile_update"] == {}

    def test_empty_string_input(self):
        """Empty string input returns empty message with defaults."""
        result = parse_llm_response("")
        assert result["message"] == ""
        assert result["name"] is None
        assert result["profile_update"] == {}

    def test_end_call_true(self):
        """end_call=true is correctly extracted."""
        text = json.dumps({"message": "Bye!", "end_call": True})
        result = parse_llm_response(text)
        assert result["end_call"] is True

    def test_end_call_false(self):
        """end_call=false is correctly extracted."""
        text = json.dumps({"message": "Continue", "end_call": False})
        result = parse_llm_response(text)
        assert result["end_call"] is False

    def test_profile_update_with_data(self):
        """profile_update with actual data is preserved."""
        update = {"appointments": [{"date": "2024-06-15", "type": "consultation"}]}
        text = json.dumps({"message": "Noted.", "profile_update": update})
        result = parse_llm_response(text)
        assert result["profile_update"] == update


# ── Tests for LLMStreamClient sentence chunking ──────────────────────────────


def _make_stream_chunk(content: str | None):
    """Create a mock stream chunk with the given content."""
    chunk = MagicMock()
    delta = MagicMock()
    delta.content = content
    choice = MagicMock()
    choice.delta = delta
    chunk.choices = [choice]
    return chunk


class TestLLMStreamClientSentenceChunking:
    """Tests for the sentence chunking behavior of generate_response."""

    @pytest.mark.asyncio
    async def test_chunks_on_period(self):
        """Tokens are chunked at period boundaries."""
        tokens = ["Hello", " world", ".", " How", " are", " you", "?"]
        chunks_received = []

        async def on_chunk(text):
            chunks_received.append(text)

        async def on_complete(data):
            pass

        # Create mock stream
        stream_chunks = [_make_stream_chunk(t) for t in tokens]

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            cancel = asyncio.Event()
            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        # Should have chunked at "." and "?"
        assert len(chunks_received) == 2
        assert chunks_received[0] == "Hello world."
        assert chunks_received[1] == "How are you?"

    @pytest.mark.asyncio
    async def test_chunks_on_exclamation(self):
        """Tokens are chunked at exclamation mark boundaries."""
        tokens = ["Great", "!", " Let", " me", " help", "."]
        chunks_received = []

        async def on_chunk(text):
            chunks_received.append(text)

        async def on_complete(data):
            pass

        stream_chunks = [_make_stream_chunk(t) for t in tokens]

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            cancel = asyncio.Event()
            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        assert len(chunks_received) == 2
        assert chunks_received[0] == "Great!"
        assert chunks_received[1] == "Let me help."

    @pytest.mark.asyncio
    async def test_chunks_on_colon(self):
        """Tokens are chunked at colon boundaries."""
        tokens = ["Here", " is", " the", " info", ":", " name", " is", " John", "."]
        chunks_received = []

        async def on_chunk(text):
            chunks_received.append(text)

        async def on_complete(data):
            pass

        stream_chunks = [_make_stream_chunk(t) for t in tokens]

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            cancel = asyncio.Event()
            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        assert len(chunks_received) == 2
        assert chunks_received[0] == "Here is the info:"
        assert chunks_received[1] == "name is John."

    @pytest.mark.asyncio
    async def test_remaining_buffer_flushed_on_completion(self):
        """Any remaining buffer is flushed when the stream ends."""
        tokens = ["Hello", " world"]  # No sentence-ending punctuation
        chunks_received = []

        async def on_chunk(text):
            chunks_received.append(text)

        async def on_complete(data):
            pass

        stream_chunks = [_make_stream_chunk(t) for t in tokens]

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            cancel = asyncio.Event()
            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        # Should flush the remaining buffer
        assert len(chunks_received) == 1
        assert chunks_received[0] == "Hello world"

    @pytest.mark.asyncio
    async def test_cancellation_stops_stream(self):
        """Setting cancel_event stops processing the stream."""
        tokens = ["Hello", ".", " This", " should", " not", " appear", "."]
        chunks_received = []
        cancel = asyncio.Event()

        async def on_chunk(text):
            chunks_received.append(text)
            # Cancel after first chunk
            cancel.set()

        async def on_complete(data):
            pass

        stream_chunks = [_make_stream_chunk(t) for t in tokens]

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        # Only the first sentence chunk should have been received
        assert len(chunks_received) == 1
        assert chunks_received[0] == "Hello."

    @pytest.mark.asyncio
    async def test_on_complete_receives_parsed_json(self):
        """on_complete callback receives the parsed JSON response."""
        response_json = json.dumps({
            "message": "Hello!",
            "name": "Alice",
            "phone": "+1234567890",
            "notes": "Test note",
            "end_call": False,
            "profile_update": {"key": "value"},
        })
        # Simulate tokens that form the JSON
        tokens = list(response_json)  # Character by character
        complete_data = None

        async def on_chunk(text):
            pass

        async def on_complete(data):
            nonlocal complete_data
            complete_data = data

        stream_chunks = [_make_stream_chunk(t) for t in tokens]

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            cancel = asyncio.Event()
            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        assert complete_data is not None
        assert complete_data["message"] == "Hello!"
        assert complete_data["name"] == "Alice"
        assert complete_data["phone"] == "+1234567890"
        assert complete_data["notes"] == "Test note"
        assert complete_data["end_call"] is False
        assert complete_data["profile_update"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_empty_chunks_not_forwarded(self):
        """Empty or whitespace-only chunks are not forwarded."""
        tokens = [".", "  ", "Hello", "."]
        chunks_received = []

        async def on_chunk(text):
            chunks_received.append(text)

        async def on_complete(data):
            pass

        stream_chunks = [_make_stream_chunk(t) for t in tokens]

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            cancel = asyncio.Event()
            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        # "." alone is a valid chunk, "  " after "." starts new buffer, then "Hello." is flushed
        assert all(c.strip() for c in chunks_received)

    @pytest.mark.asyncio
    async def test_none_content_tokens_skipped(self):
        """Tokens with None content are skipped gracefully."""
        stream_chunks = [
            _make_stream_chunk("Hello"),
            _make_stream_chunk(None),  # role token or empty delta
            _make_stream_chunk(" world"),
            _make_stream_chunk("."),
        ]
        chunks_received = []

        async def on_chunk(text):
            chunks_received.append(text)

        async def on_complete(data):
            pass

        async def mock_stream_iter():
            for c in stream_chunks:
                yield c

        mock_stream = AsyncMock()
        mock_stream.__aiter__ = lambda self: mock_stream_iter()
        mock_stream.close = AsyncMock()

        with patch("src.realtime.llm.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_stream)

            client = LLMStreamClient(api_key="test-key")
            client._client = instance

            cancel = asyncio.Event()
            await client.generate_response(
                messages=[{"role": "user", "content": "Hi"}],
                on_sentence_chunk=on_chunk,
                on_complete=on_complete,
                cancel_event=cancel,
            )

        assert len(chunks_received) == 1
        assert chunks_received[0] == "Hello world."
