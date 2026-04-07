"""
Configuration module.
All sensitive credentials are read from the encrypted DB config table.
Env-var fallbacks are kept for migration convenience.
Only SECRET_KEY must be set as an environment variable.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# The one env var that must stay outside the DB (needed to decrypt the DB itself)
SECRET_KEY = os.environ.get("SECRET_KEY", "changeme")


def _get(db_key: str, env_key: str = "", default: str = "") -> str:
    """Read from encrypted DB, fall back to env var, then to default."""
    try:
        import db
        val = db.config_get_secure(db_key)
        if val:
            return val
    except Exception:
        pass
    if env_key:
        return os.environ.get(env_key, default)
    return default


# ── Accessor functions (lazy — read from DB on every call) ────────────────────

def account_sid() -> str:
    return _get("twilio_account_sid", "TWILIO_ACCOUNT_SID")

def auth_token() -> str:
    return _get("twilio_auth_token", "TWILIO_AUTH_TOKEN")

def openai_api_key() -> str:
    return _get("openai_api_key", "OPENAI_API_KEY")

def resend_api_key() -> str:
    return _get("resend_api_key", "RESEND_API_KEY")

def resend_from_addr() -> str:
    return _get("resend_from", "RESEND_FROM", "AI Receptionist <onboarding@resend.dev>")

def elevenlabs_api_key() -> str:
    return _get("elevenlabs_api_key", "ELEVENLABS_API_KEY")

def google_tts_api_key() -> str:
    return _get("google_tts_api_key", "GOOGLE_TTS_API_KEY")

def twilio_api_key_sid() -> str:
    return _get("twilio_api_key_sid", "TWILIO_API_KEY_SID")

def twilio_api_key_secret() -> str:
    return _get("twilio_api_key_secret", "TWILIO_API_KEY_SECRET")

def twilio_twiml_app_sid() -> str:
    return _get("twilio_twiml_app_sid", "TWILIO_TWIML_APP_SID")

def twilio_verify_sid() -> str:
    return _get("twilio_verify_sid", "TWILIO_VERIFY_SID")


# ── Client factories ──────────────────────────────────────────────────────────

def twilio_client():
    from twilio.rest import Client
    return Client(account_sid(), auth_token())

def openai_client():
    from openai import OpenAI
    return OpenAI(api_key=openai_api_key())
