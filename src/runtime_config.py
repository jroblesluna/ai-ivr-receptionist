"""
Runtime mutable configuration — persisted in SQLite (data/app.db).
On first boot the config table is seeded from data/runtime_config.json (git),
then from env-var defaults for any missing keys.
"""
import os
import db

_DEFAULTS = {
    "use_case_id":        os.environ.get("USE_CASE_ID",        "robles_ai"),
    "twilio_from":        os.environ.get("TWILIO_NUMBER",      ""),
    "forward_to":         os.environ.get("FORWARD_TO",         ""),
    "report_email":       os.environ.get("REPORT_EMAIL",       ""),
    "whatsapp_from":      os.environ.get("WHATSAPP_FROM",      ""),
    "whatsapp_to":        os.environ.get("WHATSAPP_TO",        ""),
    "notify_email":       os.environ.get("NOTIFY_EMAIL",       "0"),
    "notify_whatsapp":    os.environ.get("NOTIFY_WHATSAPP",    "1"),
    "elevenlabs_voice_id": os.environ.get("ELEVENLABS_VOICE_ID", ""),
}

# Seed env-var defaults for any keys still missing after JSON migration
db.config_seed(_DEFAULTS)


def get(key, default=None):
    return db.config_get(key, default)


def set(key, value):
    db.config_set(key, value)


def all_config() -> dict:
    return db.config_all()
