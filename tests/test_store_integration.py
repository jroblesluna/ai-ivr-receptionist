"""Unit tests for src/realtime/store_integration.py.

Tests the helper functions that bridge the real-time pipeline with the
existing Redis-backed SessionStore.
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.realtime.store_integration import (
    save_conversation_history,
    update_collected_info,
    handle_profile_update,
    _is_duplicate_item,
    _normalize_str,
    _values_match,
    _canon_key,
)


# ---------------------------------------------------------------------------
# Tests for save_conversation_history
# ---------------------------------------------------------------------------


class TestSaveConversationHistory:
    """Tests for save_conversation_history function."""

    @patch("src.realtime.store_integration.session_store")
    def test_saves_history_under_50(self, mock_store):
        """History with fewer than 50 messages is saved as-is."""
        history = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        save_conversation_history("CA123", history)
        mock_store.set_conversation.assert_called_once_with("CA123", history)

    @patch("src.realtime.store_integration.session_store")
    def test_caps_history_at_50(self, mock_store):
        """History with more than 50 messages is capped to the last 50."""
        history = [{"role": "user", "content": f"msg {i}"} for i in range(80)]
        save_conversation_history("CA123", history)
        saved = mock_store.set_conversation.call_args[0][1]
        assert len(saved) == 50
        assert saved == history[-50:]

    @patch("src.realtime.store_integration.session_store")
    def test_empty_history(self, mock_store):
        """Empty history is saved without error."""
        save_conversation_history("CA123", [])
        mock_store.set_conversation.assert_called_once_with("CA123", [])

    @patch("src.realtime.store_integration.session_store")
    def test_exactly_50_messages(self, mock_store):
        """Exactly 50 messages are saved unchanged."""
        history = [{"role": "user", "content": f"msg {i}"} for i in range(50)]
        save_conversation_history("CA123", history)
        mock_store.set_conversation.assert_called_once_with("CA123", history)


# ---------------------------------------------------------------------------
# Tests for update_collected_info
# ---------------------------------------------------------------------------


class TestUpdateCollectedInfo:
    """Tests for update_collected_info function."""

    @patch("src.realtime.store_integration.session_store")
    def test_updates_name_when_non_null(self, mock_store):
        """Non-null name in LLM response updates the info."""
        current = {"name": None, "phone": None, "notes": None, "topic": "test"}
        llm_response = {"name": "Alice", "phone": None, "notes": None}
        result = update_collected_info("CA123", llm_response, current)
        assert result["name"] == "Alice"
        assert result["phone"] is None
        assert result["topic"] == "test"

    @patch("src.realtime.store_integration.session_store")
    def test_updates_phone_when_non_null(self, mock_store):
        """Non-null phone in LLM response updates the info."""
        current = {"name": "Alice", "phone": None, "notes": None}
        llm_response = {"name": None, "phone": "+14085551234", "notes": None}
        result = update_collected_info("CA123", llm_response, current)
        assert result["name"] == "Alice"  # unchanged
        assert result["phone"] == "+14085551234"

    @patch("src.realtime.store_integration.session_store")
    def test_updates_notes_when_non_null(self, mock_store):
        """Non-null notes in LLM response updates the info."""
        current = {"name": "Alice", "phone": "+1234", "notes": None}
        llm_response = {"name": None, "phone": None, "notes": "Wants a demo"}
        result = update_collected_info("CA123", llm_response, current)
        assert result["notes"] == "Wants a demo"

    @patch("src.realtime.store_integration.session_store")
    def test_does_not_overwrite_with_null(self, mock_store):
        """Null fields in LLM response do not overwrite existing values."""
        current = {"name": "Alice", "phone": "+1234", "notes": "Old notes"}
        llm_response = {"name": None, "phone": None, "notes": None}
        result = update_collected_info("CA123", llm_response, current)
        assert result["name"] == "Alice"
        assert result["phone"] == "+1234"
        assert result["notes"] == "Old notes"

    @patch("src.realtime.store_integration.session_store")
    def test_updates_multiple_fields(self, mock_store):
        """Multiple non-null fields are all updated."""
        current = {"name": None, "phone": None, "notes": None}
        llm_response = {"name": "Bob", "phone": "+9876", "notes": "Urgent"}
        result = update_collected_info("CA123", llm_response, current)
        assert result["name"] == "Bob"
        assert result["phone"] == "+9876"
        assert result["notes"] == "Urgent"

    @patch("src.realtime.store_integration.session_store")
    def test_persists_to_redis(self, mock_store):
        """Updated info is persisted to Redis via session_store."""
        current = {"name": None, "phone": None, "notes": None}
        llm_response = {"name": "Charlie", "phone": None, "notes": None}
        update_collected_info("CA123", llm_response, current)
        mock_store.set_collected_info.assert_called_once()
        call_args = mock_store.set_collected_info.call_args[0]
        assert call_args[0] == "CA123"
        assert call_args[1]["name"] == "Charlie"

    @patch("src.realtime.store_integration.session_store")
    def test_empty_string_treated_as_falsy(self, mock_store):
        """Empty string values are treated as falsy and don't overwrite."""
        current = {"name": "Alice", "phone": "+1234", "notes": "Notes"}
        llm_response = {"name": "", "phone": "", "notes": ""}
        result = update_collected_info("CA123", llm_response, current)
        assert result["name"] == "Alice"
        assert result["phone"] == "+1234"
        assert result["notes"] == "Notes"


# ---------------------------------------------------------------------------
# Tests for handle_profile_update
# ---------------------------------------------------------------------------


class TestHandleProfileUpdate:
    """Tests for handle_profile_update function."""

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_updates_name_in_profile(self, mock_get, mock_set, mock_store):
        """Name is updated in the caller profile."""
        mock_get.return_value = {"name": "Old Name"}
        handle_profile_update(
            call_sid="CA123",
            profile_update={},
            caller_from="+14085551234",
            demo_id="demo_1",
            name="New Name",
        )
        mock_set.assert_called_once()
        saved_profile = mock_set.call_args[0][2]
        assert saved_profile["name"] == "New Name"

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_updates_phone_in_profile(self, mock_get, mock_set, mock_store):
        """Phone is updated in the caller profile."""
        mock_get.return_value = {}
        handle_profile_update(
            call_sid="CA123",
            profile_update={},
            caller_from="+14085551234",
            demo_id="demo_1",
            phone="+19876543210",
        )
        mock_set.assert_called_once()
        saved_profile = mock_set.call_args[0][2]
        assert saved_profile["phone"] == "+19876543210"

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_updates_last_notes_in_profile(self, mock_get, mock_set, mock_store):
        """Notes are stored as last_notes in the caller profile."""
        mock_get.return_value = {}
        handle_profile_update(
            call_sid="CA123",
            profile_update={},
            caller_from="+14085551234",
            demo_id="demo_1",
            notes="Interested in product X",
        )
        mock_set.assert_called_once()
        saved_profile = mock_set.call_args[0][2]
        assert saved_profile["last_notes"] == "Interested in product X"

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_no_update_without_demo_id(self, mock_get, mock_set, mock_store):
        """No profile update when demo_id is empty."""
        handle_profile_update(
            call_sid="CA123",
            profile_update={"key": "value"},
            caller_from="+14085551234",
            demo_id="",
            name="Alice",
        )
        mock_get.assert_not_called()
        mock_set.assert_not_called()

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_no_update_without_caller_from(self, mock_get, mock_set, mock_store):
        """No profile update when caller_from is empty."""
        handle_profile_update(
            call_sid="CA123",
            profile_update={"key": "value"},
            caller_from="",
            demo_id="demo_1",
            name="Alice",
        )
        mock_get.assert_not_called()
        mock_set.assert_not_called()

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_dedup_prevents_duplicate_list_items(self, mock_get, mock_set, mock_store):
        """Duplicate items in profile_update lists are not added."""
        existing_item = {"client": "Acme Corp", "date": "2024-01-15", "type": "meeting"}
        mock_get.return_value = {"activities": [existing_item]}
        # Same item with slightly different field names (Spanish)
        new_item = {"cliente": "Acme Corp", "fecha": "2024-01-15", "tipo": "meeting"}
        handle_profile_update(
            call_sid="CA123",
            profile_update={"activities": [new_item]},
            caller_from="+14085551234",
            demo_id="demo_1",
        )
        mock_set.assert_called_once()
        saved_profile = mock_set.call_args[0][2]
        # Should still have only 1 item (duplicate was skipped)
        assert len(saved_profile["activities"]) == 1

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_new_items_are_appended(self, mock_get, mock_set, mock_store):
        """Non-duplicate items in profile_update lists are appended."""
        existing_item = {"client": "Acme Corp", "date": "2024-01-15", "type": "meeting"}
        mock_get.return_value = {"activities": [existing_item]}
        new_item = {"client": "Beta Inc", "date": "2024-02-20", "type": "call"}
        handle_profile_update(
            call_sid="CA123",
            profile_update={"activities": [new_item]},
            caller_from="+14085551234",
            demo_id="demo_1",
        )
        mock_set.assert_called_once()
        saved_profile = mock_set.call_args[0][2]
        assert len(saved_profile["activities"]) == 2

    @patch("src.realtime.store_integration.session_store")
    @patch("src.db.caller_profile_set")
    @patch("src.db.caller_profile_get")
    def test_no_change_means_no_write(self, mock_get, mock_set, mock_store):
        """If nothing changed, caller_profile_set is not called."""
        mock_get.return_value = {"name": "Alice", "phone": "+1234"}
        handle_profile_update(
            call_sid="CA123",
            profile_update={},
            caller_from="+14085551234",
            demo_id="demo_1",
            name="Alice",  # same as existing
            phone="+1234",  # same as existing
        )
        mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for deduplication helpers
# ---------------------------------------------------------------------------


class TestDeduplicationHelpers:
    """Tests for the dedup helper functions."""

    def test_canon_key_english(self):
        assert _canon_key("client") == "client"
        assert _canon_key("Customer") == "client"

    def test_canon_key_spanish(self):
        assert _canon_key("cliente") == "client"
        assert _canon_key("fecha") == "date"
        assert _canon_key("tipo") == "type"

    def test_canon_key_unknown(self):
        assert _canon_key("custom_field") == "custom_field"

    def test_normalize_str_removes_accents(self):
        assert _normalize_str("café") == "cafe"
        assert _normalize_str("José") == "jose"

    def test_normalize_str_lowercases(self):
        assert _normalize_str("HELLO") == "hello"

    def test_values_match_exact(self):
        assert _values_match("hello", "hello")

    def test_values_match_fuzzy_substring(self):
        assert _values_match("Acme Corporation", "acme corp")

    def test_values_match_short_strings_no_fuzzy(self):
        # Strings shorter than 8 chars don't get fuzzy matching
        assert not _values_match("abc", "abcdef")

    def test_is_duplicate_item_same_structure(self):
        existing = [{"client": "Acme", "date": "2024-01-15"}]
        new_item = {"cliente": "Acme", "fecha": "2024-01-15"}
        assert _is_duplicate_item(new_item, existing)

    def test_is_duplicate_item_different_structure(self):
        existing = [{"client": "Acme", "date": "2024-01-15"}]
        new_item = {"client": "Acme", "type": "meeting"}
        assert not _is_duplicate_item(new_item, existing)

    def test_is_duplicate_item_empty_values(self):
        """Empty/meaningless items are treated as duplicates (skipped)."""
        existing = [{"client": "Acme"}]
        new_item = {"client": "", "date": ""}
        assert _is_duplicate_item(new_item, existing)
