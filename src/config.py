"""
Configuration module.
Secrets are loaded from AWS Secrets Manager at startup (when AWS_REGION is set)
or from environment variables for local development.
"""
import logging
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ── AWS configuration ─────────────────────────────────────────────────────────

AWS_REGION = os.environ.get("AWS_REGION", "")
AWS_SECRET_NAME = os.environ.get("AWS_SECRET_NAME", "pickup/dev/secrets")


# ── SecretsConfig class ───────────────────────────────────────────────────────

class SecretsConfig:
    """
    Fetches all secrets from AWS Secrets Manager at startup and caches in memory.
    Falls back to environment variables when AWS_REGION is not set (local dev).
    """

    _cache: dict[str, str] = {}
    _loaded: bool = False
    _use_env_fallback: bool = False

    @classmethod
    def load(cls) -> None:
        """Fetch all secrets from Secrets Manager. Called once at startup.

        When AWS_REGION is not set, enables env-var fallback mode for local
        development (reads from os.environ on each get() call).
        """
        if cls._loaded:
            return

        if not AWS_REGION:
            logger.info(
                "AWS_REGION not set — using environment variables for secrets "
                "(local development mode)"
            )
            cls._use_env_fallback = True
            cls._loaded = True
            return

        # Fetch from AWS Secrets Manager
        try:
            import boto3
            import json
            from botocore.exceptions import ClientError, EndpointConnectionError

            client = boto3.client("secretsmanager", region_name=AWS_REGION)
            response = client.get_secret_value(SecretId=AWS_SECRET_NAME)
            secret_string = response["SecretString"]
            cls._cache = json.loads(secret_string)
            cls._loaded = True
            logger.info(
                "Loaded %d secrets from Secrets Manager (%s)",
                len(cls._cache),
                AWS_SECRET_NAME,
            )
        except Exception as exc:
            logger.error(
                "Failed to load secrets from Secrets Manager "
                "(secret=%s, region=%s): %s",
                AWS_SECRET_NAME,
                AWS_REGION,
                exc,
            )
            # Terminate within 10 seconds as per requirement 6.4
            sys.exit(1)

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """Read a secret value from the in-memory cache.

        In local dev mode (AWS_REGION not set), reads from environment variables.
        """
        if not cls._loaded:
            cls.load()

        if cls._use_env_fallback:
            return os.environ.get(key, default)

        return cls._cache.get(key, default)

    @classmethod
    def reset(cls) -> None:
        """Reset state (useful for testing)."""
        cls._cache = {}
        cls._loaded = False
        cls._use_env_fallback = False


# ── Module-level SECRET_KEY for Flask session signing ─────────────────────────
# Load secrets eagerly so SECRET_KEY is available at import time for app.py

SecretsConfig.load()
SECRET_KEY = SecretsConfig.get("SECRET_KEY", "changeme")


# ── Accessor functions (public API — delegates to SecretsConfig) ──────────────

def account_sid() -> str:
    return SecretsConfig.get("TWILIO_ACCOUNT_SID")


def auth_token() -> str:
    return SecretsConfig.get("TWILIO_AUTH_TOKEN")


def openai_api_key() -> str:
    return SecretsConfig.get("OPENAI_API_KEY")


def resend_api_key() -> str:
    return SecretsConfig.get("RESEND_API_KEY")


def resend_from_addr() -> str:
    return SecretsConfig.get(
        "RESEND_FROM", "AI Receptionist <onboarding@resend.dev>"
    )


def elevenlabs_api_key() -> str:
    return SecretsConfig.get("ELEVENLABS_API_KEY")


def google_tts_api_key() -> str:
    return SecretsConfig.get("GOOGLE_TTS_API_KEY")


def twilio_api_key_sid() -> str:
    return SecretsConfig.get("TWILIO_API_KEY_SID")


def twilio_api_key_secret() -> str:
    return SecretsConfig.get("TWILIO_API_KEY_SECRET")


def twilio_twiml_app_sid() -> str:
    return SecretsConfig.get("TWILIO_TWIML_APP_SID")


def twilio_verify_sid() -> str:
    return SecretsConfig.get("TWILIO_VERIFY_SID")


def admin_password() -> str:
    return SecretsConfig.get("ADMIN_PASSWORD")


def database_url() -> str:
    return SecretsConfig.get("DATABASE_URL")


# ── Client factories ──────────────────────────────────────────────────────────

def twilio_client():
    from twilio.rest import Client
    return Client(account_sid(), auth_token())


def openai_client():
    from openai import OpenAI
    return OpenAI(api_key=openai_api_key())
