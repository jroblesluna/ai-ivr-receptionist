"""Unit tests for src/realtime/playback.py."""

from src.realtime.playback import PlaybackTracker


class TestPlaybackTracker:
    """Tests for PlaybackTracker class."""

    def test_initial_state_is_empty(self):
        tracker = PlaybackTracker()
        assert tracker.get_partial_text_at_interruption() == ""

    def test_record_single_chunk(self):
        tracker = PlaybackTracker()
        tracker.record_chunk_sent("chunk_001", "Hello, how can I help you?")
        assert tracker.get_partial_text_at_interruption() == "Hello, how can I help you?"

    def test_record_multiple_chunks_concatenates_text(self):
        tracker = PlaybackTracker()
        tracker.record_chunk_sent("chunk_001", "Hello. ")
        tracker.record_chunk_sent("chunk_002", "How can I help you today? ")
        tracker.record_chunk_sent("chunk_003", "I'm here to assist.")
        expected = "Hello. How can I help you today? I'm here to assist."
        assert tracker.get_partial_text_at_interruption() == expected

    def test_clear_resets_tracker(self):
        tracker = PlaybackTracker()
        tracker.record_chunk_sent("chunk_001", "First turn response.")
        tracker.clear()
        assert tracker.get_partial_text_at_interruption() == ""

    def test_record_after_clear(self):
        tracker = PlaybackTracker()
        tracker.record_chunk_sent("chunk_001", "First turn. ")
        tracker.clear()
        tracker.record_chunk_sent("chunk_002", "Second turn.")
        assert tracker.get_partial_text_at_interruption() == "Second turn."

    def test_empty_text_segment(self):
        tracker = PlaybackTracker()
        tracker.record_chunk_sent("chunk_001", "")
        tracker.record_chunk_sent("chunk_002", "Some text.")
        assert tracker.get_partial_text_at_interruption() == "Some text."

    def test_multiple_clears(self):
        tracker = PlaybackTracker()
        tracker.record_chunk_sent("chunk_001", "Text.")
        tracker.clear()
        tracker.clear()
        assert tracker.get_partial_text_at_interruption() == ""
