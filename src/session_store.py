"""Redis-backed call session state store.

Replaces the in-memory Python dicts in state.py with a Redis backend
that supports multiple Gunicorn workers and persists across deploys.
"""

import json
import logging
import os

import redis

logger = logging.getLogger(__name__)

# TTL for all session keys: 2 hours
_TTL_SECONDS = 7200

# Maximum conversation messages per session
_MAX_CONVERSATION = 50

# Redis connection timeout
_CONNECT_TIMEOUT = 2


def _build_redis_client() -> redis.Redis:
    """Create a Redis client from REDIS_URL env var."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(
        url,
        socket_connect_timeout=_CONNECT_TIMEOUT,
        socket_timeout=_CONNECT_TIMEOUT,
        decode_responses=True,
    )


class SessionStore:
    """Redis-backed call session state."""

    def __init__(self, client: redis.Redis | None = None):
        self._redis = client or _build_redis_client()

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def get_conversation(self, call_sid: str) -> list[dict]:
        """Retrieve conversation history for a call session.

        Returns an empty list if the key does not exist (fresh session).
        """
        try:
            raw = self._redis.get(f"session:{call_sid}:conversation")
            if raw is None:
                return []
            return json.loads(raw)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in get_conversation: %s", exc)
            raise
        except (json.JSONDecodeError, TypeError):
            return []

    def set_conversation(self, call_sid: str, messages: list[dict]) -> None:
        """Store conversation history, capped at 50 messages."""
        try:
            capped = messages[-_MAX_CONVERSATION:]
            key = f"session:{call_sid}:conversation"
            self._redis.set(key, json.dumps(capped), ex=_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in set_conversation: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Collected caller info
    # ------------------------------------------------------------------

    def get_collected_info(self, call_sid: str) -> dict:
        """Retrieve collected caller info for a session.

        Returns a fresh info dict if the key does not exist.
        """
        try:
            raw = self._redis.get(f"session:{call_sid}:info")
            if raw is None:
                return self._fresh_info()
            return json.loads(raw)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in get_collected_info: %s", exc)
            raise
        except (json.JSONDecodeError, TypeError):
            return self._fresh_info()

    def set_collected_info(self, call_sid: str, info: dict) -> None:
        """Store collected caller info."""
        try:
            key = f"session:{call_sid}:info"
            self._redis.set(key, json.dumps(info), ex=_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in set_collected_info: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Outbound calls
    # ------------------------------------------------------------------

    def add_outbound_call(self, room: str, call_sid: str) -> None:
        """Record an outbound call SID for a room."""
        try:
            self._redis.set(f"outbound:{room}", call_sid, ex=_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in add_outbound_call: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Room state flags
    # ------------------------------------------------------------------

    def mark_failed_room(self, room: str) -> None:
        """Mark a room as failed (agent did not answer)."""
        try:
            self._redis.set(f"room:failed:{room}", "1", ex=_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in mark_failed_room: %s", exc)
            raise

    def mark_briefed_room(self, room: str) -> None:
        """Mark a room as briefed (operator answered)."""
        try:
            self._redis.set(f"room:briefed:{room}", "1", ex=_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in mark_briefed_room: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Machine detection counter
    # ------------------------------------------------------------------

    def get_machine_count(self, room: str) -> int:
        """Get the number of times voicemail/machine was detected for a room."""
        try:
            val = self._redis.get(f"room:machine:{room}")
            if val is None:
                return 0
            return int(val)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in get_machine_count: %s", exc)
            raise

    def increment_machine_count(self, room: str) -> int:
        """Increment machine detection counter and return new value."""
        try:
            key = f"room:machine:{room}"
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, _TTL_SECONDS)
            results = pipe.execute()
            return int(results[0])
        except redis.RedisError as exc:
            logger.error("Redis unavailable in increment_machine_count: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Intro played flag
    # ------------------------------------------------------------------

    def mark_intro_played(self, call_sid: str) -> None:
        """Mark that the intro audio has been played for a call."""
        try:
            self._redis.set(f"intro:{call_sid}", "1", ex=_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in mark_intro_played: %s", exc)
            raise

    def has_intro_played(self, call_sid: str) -> bool:
        """Check whether the intro audio has already been played."""
        try:
            return self._redis.exists(f"intro:{call_sid}") > 0
        except redis.RedisError as exc:
            logger.error("Redis unavailable in has_intro_played: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Outbound calls (additional)
    # ------------------------------------------------------------------

    def get_outbound_call(self, room: str) -> str | None:
        """Get the outbound call SID for a room, or None if not set."""
        try:
            return self._redis.get(f"outbound:{room}")
        except redis.RedisError as exc:
            logger.error("Redis unavailable in get_outbound_call: %s", exc)
            raise

    def remove_outbound_call(self, room: str) -> None:
        """Remove the outbound call mapping for a room."""
        try:
            self._redis.delete(f"outbound:{room}")
        except redis.RedisError as exc:
            logger.error("Redis unavailable in remove_outbound_call: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Room state flags (additional query/clear methods)
    # ------------------------------------------------------------------

    def is_failed_room(self, room: str) -> bool:
        """Check whether a room is marked as failed."""
        try:
            return self._redis.exists(f"room:failed:{room}") > 0
        except redis.RedisError as exc:
            logger.error("Redis unavailable in is_failed_room: %s", exc)
            raise

    def clear_failed_room(self, room: str) -> None:
        """Remove the failed flag from a room."""
        try:
            self._redis.delete(f"room:failed:{room}")
        except redis.RedisError as exc:
            logger.error("Redis unavailable in clear_failed_room: %s", exc)
            raise

    def is_briefed_room(self, room: str) -> bool:
        """Check whether a room is marked as briefed."""
        try:
            return self._redis.exists(f"room:briefed:{room}") > 0
        except redis.RedisError as exc:
            logger.error("Redis unavailable in is_briefed_room: %s", exc)
            raise

    def clear_briefed_room(self, room: str) -> None:
        """Remove the briefed flag from a room."""
        try:
            self._redis.delete(f"room:briefed:{room}")
        except redis.RedisError as exc:
            logger.error("Redis unavailable in clear_briefed_room: %s", exc)
            raise

    def clear_machine_count(self, room: str) -> None:
        """Remove the machine detection counter for a room."""
        try:
            self._redis.delete(f"room:machine:{room}")
        except redis.RedisError as exc:
            logger.error("Redis unavailable in clear_machine_count: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Conversation (additional)
    # ------------------------------------------------------------------

    def has_conversation(self, call_sid: str) -> bool:
        """Check whether a conversation exists for a call session."""
        try:
            return self._redis.exists(f"session:{call_sid}:conversation") > 0
        except redis.RedisError as exc:
            logger.error("Redis unavailable in has_conversation: %s", exc)
            raise

    def pop_conversation(self, call_sid: str) -> list[dict]:
        """Retrieve and delete conversation history for a call session."""
        try:
            key = f"session:{call_sid}:conversation"
            raw = self._redis.get(key)
            self._redis.delete(key)
            if raw is None:
                return []
            return json.loads(raw)
        except redis.RedisError as exc:
            logger.error("Redis unavailable in pop_conversation: %s", exc)
            raise
        except (json.JSONDecodeError, TypeError):
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fresh_info() -> dict:
        """Return a blank collected-info record for a new session."""
        return {
            "name": None,
            "phone": None,
            "notes": None,
            "topic": "",
            "lang": "",
        }


# Module-level singleton instance for use by route handlers.
# Import this in route files: `from session_store import session_store`
session_store = SessionStore()
