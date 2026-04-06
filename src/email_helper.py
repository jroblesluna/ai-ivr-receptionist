import os
import requests
import runtime_config

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM    = os.environ.get("RESEND_FROM", "AI Receptionist <onboarding@resend.dev>")


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
            print(f"[EMAIL] Report sent to {report_email}")
        else:
            print(f"[EMAIL ERROR] Resend returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
