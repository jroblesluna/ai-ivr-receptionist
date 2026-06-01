"""Playback tracker for the real-time voice conversation pipeline.

Tracks which TTS audio chunks have been sent to Twilio, enabling accurate
interruption handling during barge-in events. When the caller interrupts,
the tracker provides the partial text that was spoken before the interruption.
"""

from __future__ import annotations


class PlaybackTracker:
    """Tracks TTS audio chunks sent to Twilio for interruption handling.

    Maintains an ordered list of (chunk_id, text_segment) tuples representing
    audio that has been sent to the caller. This allows the pipeline to know
    exactly what text the caller heard before a barge-in event.
    """

    def __init__(self) -> None:
        self._sent_chunks: list[tuple[str, str]] = []

    def record_chunk_sent(self, chunk_id: str, text_segment: str) -> None:
        """Record that an audio chunk has been sent to Twilio.

        Args:
            chunk_id: Unique identifier for the audio chunk (used with Twilio mark events).
            text_segment: The text content that this audio chunk represents.
        """
        self._sent_chunks.append((chunk_id, text_segment))

    def get_partial_text_at_interruption(self) -> str:
        """Return the concatenated text of all chunks sent before a barge-in.

        Returns:
            The full text that the caller has heard up to the point of interruption.
        """
        return "".join(text for _, text in self._sent_chunks)

    def clear(self) -> None:
        """Reset the tracker for the next conversation turn."""
        self._sent_chunks = []
