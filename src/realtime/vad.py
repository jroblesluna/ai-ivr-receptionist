"""Voice Activity Detection using Silero VAD model.

Processes inbound audio frames from Twilio (mulaw 8kHz) and detects
when the caller starts or stops speaking. Audio is converted from
mulaw 8kHz to 16-bit PCM 16kHz as required by Silero VAD.

Silero VAD requires a minimum of 512 samples at 16kHz (32ms). Since
Twilio media frames are typically 160 bytes of mulaw (20ms at 8kHz),
which yields only 320 samples at 16kHz after resampling, this processor
buffers incoming audio until enough samples are accumulated for a valid
VAD inference.
"""

from __future__ import annotations

from enum import Enum

try:
    import audioop
except ModuleNotFoundError:  # Python 3.13+ removed audioop
    import audioop_lts as audioop  # type: ignore[no-redef]

import torch
import torchaudio


# Silero VAD requires chunks of exactly 512 samples at 16kHz
_SILERO_CHUNK_SAMPLES = 512
_SILERO_SAMPLE_RATE = 16000


class VADEvent(Enum):
    """Events emitted by the VAD processor on state transitions."""

    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"


class VADProcessor:
    """Voice Activity Detection using Silero VAD model.

    Processes mulaw 8kHz audio frames (as received from Twilio Media Streams)
    and emits SPEECH_START / SPEECH_END events based on voice activity.

    Audio frames are buffered internally until enough samples are accumulated
    for a valid Silero VAD inference (512 samples at 16kHz = 32ms).

    Args:
        threshold: Confidence threshold for speech detection (default 0.5).
        silence_duration_ms: Milliseconds of silence before emitting SPEECH_END (default 300).
        sample_rate_in: Input sample rate from Twilio (8000 Hz).
        sample_rate_out: Sample rate expected by Silero VAD (16000 Hz).
    """

    def __init__(
        self,
        threshold: float = 0.5,
        silence_duration_ms: int = 300,
        sample_rate_in: int = 8000,
        sample_rate_out: int = _SILERO_SAMPLE_RATE,
    ) -> None:
        self.threshold = threshold
        self.silence_duration_ms = silence_duration_ms
        self.sample_rate_in = sample_rate_in
        self.sample_rate_out = sample_rate_out

        # Load Silero VAD model (cached after first download)
        self._model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )

        # Resampler: 8kHz → 16kHz
        self._resampler = torchaudio.transforms.Resample(
            orig_freq=self.sample_rate_in,
            new_freq=self.sample_rate_out,
        )

        # Internal state
        self._is_speaking: bool = False
        self._silence_frames_count: float = 0.0
        self._audio_buffer: torch.Tensor = torch.tensor([], dtype=torch.float32)

    @property
    def is_speaking(self) -> bool:
        """Whether the VAD currently considers the caller to be speaking."""
        return self._is_speaking

    def _convert_mulaw_to_pcm16k(self, audio_frame: bytes) -> torch.Tensor:
        """Convert mulaw 8kHz audio bytes to a float32 tensor at 16kHz.

        Steps:
            1. Decode mulaw → 16-bit PCM (linear) at 8kHz using audioop
            2. Convert raw PCM bytes to a torch tensor
            3. Resample from 8kHz to 16kHz
        """
        # Decode mulaw to 16-bit linear PCM
        pcm_bytes = audioop.ulaw2lin(audio_frame, 2)

        # Convert to torch tensor (int16 → float32 normalized to [-1, 1])
        pcm_tensor = torch.frombuffer(bytearray(pcm_bytes), dtype=torch.int16).float() / 32768.0

        # Resample 8kHz → 16kHz
        pcm_16k = self._resampler(pcm_tensor)

        return pcm_16k

    def process_frame(self, audio_frame: bytes) -> VADEvent | None:
        """Process a single audio frame and return a VAD event if a state transition occurs.

        Audio is buffered internally until enough samples are accumulated for
        Silero VAD inference (512 samples at 16kHz). Multiple VAD chunks may be
        processed from a single call if the buffer has accumulated enough data.

        Args:
            audio_frame: Raw mulaw-encoded audio bytes at 8kHz from Twilio.

        Returns:
            VADEvent.SPEECH_START if speech is newly detected,
            VADEvent.SPEECH_END if silence duration threshold is reached,
            or None if no state transition occurs.
        """
        # Convert mulaw 8kHz → float32 PCM 16kHz and append to buffer
        pcm_16k = self._convert_mulaw_to_pcm16k(audio_frame)
        self._audio_buffer = torch.cat([self._audio_buffer, pcm_16k])

        # Process all complete chunks in the buffer
        event: VADEvent | None = None

        while len(self._audio_buffer) >= _SILERO_CHUNK_SAMPLES:
            chunk = self._audio_buffer[:_SILERO_CHUNK_SAMPLES]
            self._audio_buffer = self._audio_buffer[_SILERO_CHUNK_SAMPLES:]

            # Run Silero VAD inference
            confidence = self._model(chunk, self.sample_rate_out).item()

            # Duration of this chunk in milliseconds
            chunk_duration_ms = (_SILERO_CHUNK_SAMPLES / self.sample_rate_out) * 1000.0

            if confidence >= self.threshold:
                # Speech detected
                self._silence_frames_count = 0.0

                if not self._is_speaking:
                    self._is_speaking = True
                    event = VADEvent.SPEECH_START

            else:
                # Silence detected
                if self._is_speaking:
                    self._silence_frames_count += chunk_duration_ms

                    if self._silence_frames_count >= self.silence_duration_ms:
                        self._is_speaking = False
                        self._silence_frames_count = 0.0
                        event = VADEvent.SPEECH_END

        return event

    def reset(self) -> None:
        """Clear internal state between turns.

        Resets the speaking flag, silence counter, audio buffer, and the
        Silero model's internal hidden state so the processor can be reused
        cleanly.
        """
        self._is_speaking = False
        self._silence_frames_count = 0.0
        self._audio_buffer = torch.tensor([], dtype=torch.float32)
        self._model.reset_states()
