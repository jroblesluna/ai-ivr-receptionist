"""Unit tests for the VADProcessor class.

Tests the Voice Activity Detection processor including audio conversion,
state transitions, and reset behavior.
"""

import sys
import os
import struct

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop  # type: ignore[no-redef]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import torch

from src.realtime.vad import VADEvent, VADProcessor, _SILERO_CHUNK_SAMPLES


def _make_mulaw_silence(num_samples: int = 160) -> bytes:
    """Create a mulaw-encoded silence frame (num_samples at 8kHz)."""
    pcm_silence = b"\x00\x00" * num_samples
    return audioop.lin2ulaw(pcm_silence, 2)


def _make_mulaw_tone(num_samples: int = 160, frequency: int = 440) -> bytes:
    """Create a mulaw-encoded tone frame (num_samples at 8kHz).

    Generates a sine wave at the given frequency to simulate speech-like audio.
    """
    import math

    sample_rate = 8000
    samples = []
    for i in range(num_samples):
        value = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(struct.pack("<h", value))
    pcm_bytes = b"".join(samples)
    return audioop.lin2ulaw(pcm_bytes, 2)


class TestVADProcessorInit:
    """Test VADProcessor initialization and configuration."""

    def test_default_threshold(self):
        """VADProcessor uses 0.5 threshold by default."""
        vad = VADProcessor()
        assert vad.threshold == 0.5

    def test_default_silence_duration(self):
        """VADProcessor uses 300ms silence duration by default."""
        vad = VADProcessor()
        assert vad.silence_duration_ms == 300

    def test_custom_threshold(self):
        """VADProcessor accepts custom threshold."""
        vad = VADProcessor(threshold=0.7)
        assert vad.threshold == 0.7

    def test_custom_silence_duration(self):
        """VADProcessor accepts custom silence duration."""
        vad = VADProcessor(silence_duration_ms=500)
        assert vad.silence_duration_ms == 500

    def test_initial_state_not_speaking(self):
        """VADProcessor starts in non-speaking state."""
        vad = VADProcessor()
        assert vad.is_speaking is False

    def test_sample_rates(self):
        """VADProcessor has correct default sample rates."""
        vad = VADProcessor()
        assert vad.sample_rate_in == 8000
        assert vad.sample_rate_out == 16000


class TestVADProcessorAudioConversion:
    """Test the mulaw 8kHz → PCM 16kHz conversion."""

    def test_convert_mulaw_produces_tensor(self):
        """Converting mulaw bytes produces a torch tensor."""
        vad = VADProcessor()
        mulaw_frame = _make_mulaw_silence(160)

        result = vad._convert_mulaw_to_pcm16k(mulaw_frame)
        assert isinstance(result, torch.Tensor)
        assert result.dtype == torch.float32

    def test_convert_mulaw_resamples_to_16k(self):
        """Conversion resamples from 8kHz to 16kHz (doubles sample count)."""
        vad = VADProcessor()
        # 160 samples at 8kHz → should be 320 samples at 16kHz
        mulaw_frame = _make_mulaw_silence(160)

        result = vad._convert_mulaw_to_pcm16k(mulaw_frame)
        assert len(result) == 320

    def test_convert_mulaw_silence_near_zero(self):
        """Silence frames convert to values near zero."""
        vad = VADProcessor()
        mulaw_frame = _make_mulaw_silence(160)

        result = vad._convert_mulaw_to_pcm16k(mulaw_frame)
        # Silence should produce values very close to zero
        # (mulaw encodes 0 as a small non-zero value due to companding)
        assert result.abs().max().item() < 0.01


class TestVADProcessorReset:
    """Test the reset() method."""

    def test_reset_clears_speaking_state(self):
        """reset() sets is_speaking to False."""
        vad = VADProcessor()
        vad._is_speaking = True
        vad.reset()
        assert vad.is_speaking is False

    def test_reset_clears_silence_counter(self):
        """reset() resets the silence frame counter."""
        vad = VADProcessor()
        vad._silence_frames_count = 150.0
        vad.reset()
        assert vad._silence_frames_count == 0.0

    def test_reset_clears_audio_buffer(self):
        """reset() clears the internal audio buffer."""
        vad = VADProcessor()
        vad._audio_buffer = torch.ones(100)
        vad.reset()
        assert len(vad._audio_buffer) == 0


class TestVADProcessorProcessFrame:
    """Test process_frame state transitions."""

    def test_short_silence_frame_returns_none(self):
        """Processing a short silence frame (not enough for VAD chunk) returns None."""
        vad = VADProcessor()
        # 160 mulaw samples → 320 samples at 16kHz, less than 512 needed
        silence_mulaw = _make_mulaw_silence(160)
        result = vad.process_frame(silence_mulaw)
        # Buffer hasn't accumulated enough for inference yet
        assert result is None

    def test_sufficient_silence_returns_none_when_not_speaking(self):
        """Processing enough silence frames when not speaking returns None."""
        vad = VADProcessor()
        # Feed enough frames to trigger at least one VAD inference
        # 512 samples at 16kHz = 256 samples at 8kHz
        silence_mulaw = _make_mulaw_silence(256)
        result = vad.process_frame(silence_mulaw)
        # Silence when not speaking → no state transition
        assert result is None
        assert vad.is_speaking is False

    def test_process_frame_returns_vad_event_or_none(self):
        """process_frame always returns a VADEvent or None."""
        vad = VADProcessor()
        silence_mulaw = _make_mulaw_silence(256)
        result = vad.process_frame(silence_mulaw)
        assert result is None or isinstance(result, VADEvent)

    def test_buffer_accumulates_across_frames(self):
        """Audio buffer accumulates across multiple process_frame calls."""
        vad = VADProcessor()
        # First frame: 160 mulaw → 320 samples at 16kHz (not enough)
        silence_mulaw = _make_mulaw_silence(160)
        vad.process_frame(silence_mulaw)

        # After processing, buffer should have leftover samples
        # (320 < 512, so no inference happened, buffer retains 320 samples)
        # But after second frame, buffer has 640 → one chunk processed, 128 left
        vad.process_frame(silence_mulaw)
        # 640 - 512 = 128 samples remaining in buffer
        assert len(vad._audio_buffer) == 128


class TestVADEvent:
    """Test VADEvent enum values."""

    def test_speech_start_value(self):
        """SPEECH_START has correct string value."""
        assert VADEvent.SPEECH_START.value == "speech_start"

    def test_speech_end_value(self):
        """SPEECH_END has correct string value."""
        assert VADEvent.SPEECH_END.value == "speech_end"

    def test_enum_members(self):
        """VADEvent has exactly two members."""
        assert len(VADEvent) == 2
