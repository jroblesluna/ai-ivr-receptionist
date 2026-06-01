"""Session store integration for the real-time voice pipeline.

Provides helper functions that bridge the real-time pipeline with the existing
Redis-backed SessionStore, ensuring conversation history, collected info, and
caller profile updates are persisted using the same key format and logic as
the Flask-based ai_respond route.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.realtime.models import cap_conversation_history
from src.session_store import session_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deduplication helpers (mirrored from src/routes/ai.py)
# ---------------------------------------------------------------------------

_DETAIL_FIELDS = frozenset({
    "detalle", "details", "description", "descripcion",
    "notes", "nota", "notas", "comment", "comentario", "summary", "resumen",
})

_KEY_CANON = {
    "client": "client", "cliente": "client", "customer": "client", "cliente_nombre": "client",
    "date": "date", "fecha": "date", "fecha_iso": "date", "day": "date", "dia": "date",
    "type": "type", "tipo": "type", "kind": "type", "categoria": "type", "category": "type",
    "product": "product", "producto": "product", "item": "product", "articulo": "product",
    "quantity": "qty", "cantidad": "qty", "qty": "qty", "amount": "qty", "monto": "qty",
    "status": "status", "estado": "status", "state": "status",
    "name": "name", "nombre": "name",
    "detail": "detail", "detalle": "detail", "details": "detail",
    "description": "detail", "descripcion": "detail",
    "notes": "detail", "nota": "detail", "notas": "detail",
    "comment": "detail", "comentario": "detail",
    "summary": "detail", "resumen": "detail",
}


def _canon_key(k: str) -> str:
    return _KEY_CANON.get(k.lower(), k.lower())


def _normalize_str(s: str) -> str:
    """Lowercase, strip accents and non-alphanumeric for fuzzy comparison."""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_str.lower())


def _values_match(a: str, b: str) -> bool:
    """Exact or fuzzy substring match for identifying field values."""
    na, nb = _normalize_str(a), _normalize_str(b)
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 8 and shorter in longer


def _is_duplicate_item(new_item: dict, existing_list: list) -> bool:
    """Cross-call deduplication for profile_update list items.

    Same algorithm as the existing ai_respond route:
    - Canonicalise field names via _KEY_CANON (ES/EN bilingual normalisation).
    - Exclude free-text detail fields from the identity comparison.
    - Require the same canonical key set to match.
    - Use fuzzy value matching for entity name strings.
    """
    def _canon_id(item: dict) -> dict:
        result = {}
        for k, v in item.items():
            ck = _canon_key(k)
            if ck not in _DETAIL_FIELDS and ck != "detail":
                result[ck] = v
        return result

    new_id = _canon_id(new_item)
    if not any(v for v in new_id.values()):
        return True  # empty/meaningless item — skip
    for existing in existing_list:
        if not isinstance(existing, dict):
            continue
        ex_id = _canon_id(existing)
        if set(new_id.keys()) != set(ex_id.keys()):
            continue
        if all(_values_match(str(new_id[k]), str(ex_id[k])) for k in new_id):
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_conversation_history(call_sid: str, history: list[dict]) -> None:
    """Save conversation history to Redis, capped at 50 messages.

    Uses the same key format as the existing system:
    ``session:{call_sid}:conversation``

    Args:
        call_sid: The Twilio call SID identifying the session.
        history: The full conversation history (system + user + assistant messages).
    """
    capped = cap_conversation_history(history)
    session_store.set_conversation(call_sid, capped)
    logger.debug(
        "Conversation history saved",
        extra={"call_sid": call_sid, "message_count": len(capped)},
    )


def update_collected_info(
    call_sid: str,
    llm_response: dict[str, Any],
    current_info: dict[str, Any],
) -> dict[str, Any]:
    """Update collected caller info in Redis with non-null fields from LLM response.

    Only overwrites fields that are non-null in the LLM response, leaving all
    other fields unchanged. Persists the updated info to Redis.

    Args:
        call_sid: The Twilio call SID identifying the session.
        llm_response: Parsed LLM response dict (may contain name, phone, notes).
        current_info: The current collected info dict from the session.

    Returns:
        The updated info dict after applying non-null fields.
    """
    updated = dict(current_info)

    name = llm_response.get("name")
    phone = llm_response.get("phone")
    notes = llm_response.get("notes")

    if name:
        updated["name"] = name
    if phone:
        updated["phone"] = phone
    if notes:
        updated["notes"] = notes

    session_store.set_collected_info(call_sid, updated)
    logger.debug(
        "Collected info updated",
        extra={
            "call_sid": call_sid,
            "updated_fields": [
                f for f in ("name", "phone", "notes")
                if llm_response.get(f)
            ],
        },
    )
    return updated


def handle_profile_update(
    call_sid: str,
    profile_update: dict[str, Any],
    caller_from: str,
    demo_id: str = "",
    name: str | None = None,
    phone: str | None = None,
    notes: str | None = None,
) -> None:
    """Apply profile update with deduplication logic matching the existing ai_respond route.

    Updates the caller profile in the database using the same dedup algorithm
    as the Flask route: canonicalises field names, excludes detail fields from
    identity comparison, and uses fuzzy value matching.

    Args:
        call_sid: The Twilio call SID (for logging).
        profile_update: The profile_update dict from the LLM response.
        caller_from: The caller's phone number (E.164 format).
        demo_id: The demo use case ID.
        name: Caller name extracted from LLM response (or None).
        phone: Caller phone extracted from LLM response (or None).
        notes: Notes extracted from LLM response (or None).
    """
    if not demo_id or not caller_from:
        return

    import src.db as db

    existing_profile = db.caller_profile_get(caller_from, demo_id)
    changed = False

    if name and existing_profile.get("name") != name:
        existing_profile["name"] = name
        changed = True
    if phone and existing_profile.get("phone") != phone:
        existing_profile["phone"] = phone
        changed = True
    if notes and existing_profile.get("last_notes") != notes:
        existing_profile["last_notes"] = notes
        changed = True

    if isinstance(profile_update, dict) and profile_update:
        for k, v in profile_update.items():
            if isinstance(v, list) and isinstance(existing_profile.get(k), list):
                existing_list = existing_profile[k]
                for item in v:
                    if not isinstance(item, dict):
                        continue
                    if not _is_duplicate_item(item, existing_list):
                        existing_list.append(item)
                existing_profile[k] = existing_list
            else:
                existing_profile[k] = v
        changed = True

    if changed:
        try:
            tz = ZoneInfo("America/Lima")
        except Exception:
            tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        db.caller_profile_set(
            caller_from,
            demo_id,
            existing_profile,
            updated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        logger.info(
            "Caller profile updated",
            extra={"call_sid": call_sid, "caller_from": caller_from, "demo_id": demo_id},
        )
