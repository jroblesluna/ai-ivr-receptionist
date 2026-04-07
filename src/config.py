import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from twilio.rest import Client
from openai import OpenAI

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN",  "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
openai_client  = OpenAI(api_key=OPENAI_API_KEY)

SECRET_KEY     = os.environ.get("SECRET_KEY",     "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

TWILIO_API_KEY_SID    = os.environ.get("TWILIO_API_KEY_SID",    "")
TWILIO_API_KEY_SECRET = os.environ.get("TWILIO_API_KEY_SECRET", "")
TWILIO_TWIML_APP_SID  = os.environ.get("TWILIO_TWIML_APP_SID",  "")
TWILIO_VERIFY_SID     = os.environ.get("TWILIO_VERIFY_SID",     "")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

SMTP_HOST     = os.environ.get("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER",     "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM     = os.environ.get("SMTP_FROM",     SMTP_USER)


def twilio_client():
    return Client(ACCOUNT_SID, AUTH_TOKEN)
