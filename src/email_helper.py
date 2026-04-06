import os
import requests
import runtime_config

RESEND_STARTER_URL = os.environ.get("RESEND_STARTER_URL", "")


def send_report_email(subject: str, body: str) -> None:
    """Send a report email via Railway Resend Starter service."""
    if runtime_config.get("notify_email") != "1":
        print("[EMAIL] Email notifications disabled — skipping.")
        return

    if not RESEND_STARTER_URL:
        print("[EMAIL] RESEND_STARTER_URL not configured — skipping email.")
        return

    report_email = runtime_config.get("report_email") or ""
    if not report_email:
        print("[EMAIL] report_email not configured — skipping email.")
        return

    try:
        resp = requests.post(
            f"{RESEND_STARTER_URL.rstrip('/')}/api/emails",
            json={
                "to": report_email,
                "subject": subject,
                "html": body.replace("\n", "<br>"),
            },
            timeout=15,
        )
        if resp.ok:
            print(f"[EMAIL] Report sent to {report_email}")
        else:
            print(f"[EMAIL ERROR] Resend Starter returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
