# Feature: aws-migration, Property 1: Session state round-trip preservation
"""
Property-based test for session state round-trip preservation.

For any valid call session data (conversation history of 0–50 messages,
collected caller info with arbitrary string fields, and room state flags),
storing the session in Redis and then retrieving it should produce data
identical to the original.

**Validates: Requirements 3.1**
"""
import sys
import os

import pytest
import fakeredis
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.session_store import SessionStore


# ── Strategies ────────────────────────────────────────────────────────────────

# Safe text that avoids null bytes (invalid in JSON strings)
safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=200,
)

safe_text_short = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=50,
)

# A single conversation message with "role" and "content" fields
message_strategy = st.fixed_dictionaries({
    "role": st.sampled_from(["system", "user", "assistant"]),
    "content": safe_text,
})

# Conversation history: 0–50 messages
conversation_strategy = st.lists(message_strategy, min_size=0, max_size=50)

# Collected caller info dict — all fields optional strings
collected_info_strategy = st.fixed_dictionaries({
    "name": st.one_of(st.none(), safe_text_short),
    "phone": st.one_of(st.none(), safe_text_short),
    "notes": st.one_of(st.none(), safe_text),
    "topic": safe_text_short,
    "lang": st.sampled_from(["", "en", "es"]),
})

# Room state flags
room_state_strategy = st.fixed_dictionaries({
    "failed": st.booleans(),
    "briefed": st.booleans(),
    "machine_count": st.integers(min_value=0, max_value=10),
})

# Intro played flag
intro_played_strategy = st.booleans()

# Call SID / room identifiers
call_sid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=5,
    max_size=34,
)

room_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=3,
    max_size=30,
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_store():
    """Create a fresh SessionStore backed by a new fakeredis instance."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    return SessionStore(client=fake_redis)


# ── Property Test ─────────────────────────────────────────────────────────────

class TestSessionRoundTrip:
    """Property 1: Session state round-trip preservation.

    For any valid call session data, storing the session in Redis and then
    retrieving it should produce data identical to the original.

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        conversation=conversation_strategy,
    )
    def test_conversation_round_trip(self, call_sid, conversation):
        """Conversation history survives a store/retrieve round-trip."""
        store = _make_store()
        store.set_conversation(call_sid, conversation)
        retrieved = store.get_conversation(call_sid)
        assert retrieved == conversation

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        info=collected_info_strategy,
    )
    def test_collected_info_round_trip(self, call_sid, info):
        """Collected caller info survives a store/retrieve round-trip."""
        store = _make_store()
        store.set_collected_info(call_sid, info)
        retrieved = store.get_collected_info(call_sid)
        assert retrieved == info

    @settings(max_examples=100, deadline=None)
    @given(
        room=room_strategy,
        state=room_state_strategy,
    )
    def test_room_state_round_trip(self, room, state):
        """Room state flags survive a store/retrieve round-trip."""
        store = _make_store()

        # Set room state flags
        if state["failed"]:
            store.mark_failed_room(room)
        if state["briefed"]:
            store.mark_briefed_room(room)
        for _ in range(state["machine_count"]):
            store.increment_machine_count(room)

        # Retrieve and verify
        assert store.is_failed_room(room) == state["failed"]
        assert store.is_briefed_room(room) == state["briefed"]
        assert store.get_machine_count(room) == state["machine_count"]

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        intro_played=intro_played_strategy,
    )
    def test_intro_played_round_trip(self, call_sid, intro_played):
        """Intro played flag survives a store/retrieve round-trip."""
        store = _make_store()

        if intro_played:
            store.mark_intro_played(call_sid)

        assert store.has_intro_played(call_sid) == intro_played

    @settings(max_examples=100, deadline=None)
    @given(
        call_sid=call_sid_strategy,
        conversation=conversation_strategy,
        info=collected_info_strategy,
        room=room_strategy,
        state=room_state_strategy,
        intro_played=intro_played_strategy,
    )
    def test_full_session_round_trip(self, call_sid, conversation, info, room, state, intro_played):
        """A complete session (all fields) survives a store/retrieve round-trip."""
        store = _make_store()

        # Store all session data
        store.set_conversation(call_sid, conversation)
        store.set_collected_info(call_sid, info)

        if state["failed"]:
            store.mark_failed_room(room)
        if state["briefed"]:
            store.mark_briefed_room(room)
        for _ in range(state["machine_count"]):
            store.increment_machine_count(room)

        if intro_played:
            store.mark_intro_played(call_sid)

        # Retrieve and verify all data is preserved
        assert store.get_conversation(call_sid) == conversation
        assert store.get_collected_info(call_sid) == info
        assert store.is_failed_room(room) == state["failed"]
        assert store.is_briefed_room(room) == state["briefed"]
        assert store.get_machine_count(room) == state["machine_count"]
        assert store.has_intro_played(call_sid) == intro_played
