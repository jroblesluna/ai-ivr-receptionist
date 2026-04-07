import os
import requests
import runtime_config

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM    = os.environ.get("RESEND_FROM", "AI Receptionist <onboarding@resend.dev>")


def send_verification_email(to_email: str, verify_url: str, first_name: str) -> None:
    """Send an account email verification link via Resend."""
    if not RESEND_API_KEY:
        print("[EMAIL] RESEND_API_KEY not configured — skipping verification email.")
        return
    html = (
        f"<p>Hi {first_name},</p>"
        f"<p>Please verify your email address by clicking the link below:</p>"
        f"<p><a href='{verify_url}' style='color:#4f46e5;font-weight:bold;'>Verify Email</a></p>"
        f"<p>If you did not request this, you can ignore this email.</p>"
    )
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM,
                "to": [to_email],
                "subject": "Verify your email — IVR Admin",
                "html": html,
            },
            timeout=15,
        )
        if resp.ok:
            print(f"[EMAIL] Verification email sent to {to_email} | Resend ID: {resp.json().get('id','?')}")
        else:
            print(f"[EMAIL ERROR] Resend returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


def send_report_email(subject: str, body: str) -> None:
    """Send a report email via Resend API."""
    if runtime_config.get("notify_email") != "1":
        print("[EMAIL] Email notifications disabled — skipping.")
        return

    if not RESEND_API_KEY:
        print("[EMAIL] RESEND_API_KEY not configured — skipping email.")
        return

    report_email = runtime_config.get("report_email") or ""
    if not report_email:
        print("[EMAIL] report_email not configured — skipping email.")
        return

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": RESEND_FROM,
                "to": [report_email],
                "subject": subject,
                "html": body.replace("\n", "<br>"),
            },
            timeout=15,
        )
        if resp.ok:
            resend_id = resp.json().get("id", "?")
            print(f"[EMAIL] Report sent to {report_email} | Resend ID: {resend_id}")
        else:
            print(f"[EMAIL ERROR] Resend returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
