"""
Runtime mutable configuration — persisted to a JSON file so all gunicorn
workers share the same state without requiring a database.
"""
import os
import json
import threading

_LOCK = threading.Lock()
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_config.json")

_DEFAULTS = {
    "use_case_id":      os.environ.get("USE_CASE_ID",       "robles_ai"),
    "twilio_from":      os.environ.get("TWILIO_NUMBER",     ""),
    "forward_to":       os.environ.get("FORWARD_TO",        ""),
    "report_email":     os.environ.get("REPORT_EMAIL",      ""),
    "whatsapp_from":    os.environ.get("WHATSAPP_FROM",     ""),
    "whatsapp_to":      os.environ.get("WHATSAPP_TO",       ""),
    "notify_email":        os.environ.get("NOTIFY_EMAIL",        "0"),
    "notify_whatsapp":     os.environ.get("NOTIFY_WHATSAPP",     "1"),
    "elevenlabs_voice_id": os.environ.get("ELEVENLABS_VOICE_ID", ""),
}


def _load() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Fill in any keys missing from the file with env-var defaults
        added = {k: v for k, v in _DEFAULTS.items() if k not in data}
        if added:
            data.update(added)
            _save(data)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        state = dict(_DEFAULTS)
        _save(state)
        return state


def _save(state: dict):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get(key, default=None):
    return _load().get(key, default)


def set(key, value):
    with _LOCK:
        state = _load()
        state[key] = value
        _save(state)


def all_config() -> dict:
    return _load()
