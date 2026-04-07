import requests
import runtime_config
import config


def _send(to_email: str, subject: str, html: str) -> None:
    api_key = config.resend_api_key()
    from_addr = config.resend_from_addr()
    if not api_key:
        print("[EMAIL] resend_api_key not configured — skipping.")
        return
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"from": from_addr, "to": [to_email], "subject": subject, "html": html},
            timeout=15,
        )
        if resp.ok:
            print(f"[EMAIL] Sent to {to_email} | Resend ID: {resp.json().get('id','?')}")
        else:
            print(f"[EMAIL ERROR] Resend {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


def send_verification_email(to_email: str, verify_url: str, first_name: str) -> None:
    html = (
        f"<p>Hi {first_name},</p>"
        f"<p>Please verify your email address by clicking the link below:</p>"
        f"<p><a href='{verify_url}' style='color:#4f46e5;font-weight:bold;'>Verify Email →</a></p>"
        f"<p>If you did not request this, you can ignore this email.</p>"
    )
    _send(to_email, "Verify your email — IVR Admin", html)


def send_report_email(subject: str, body: str) -> None:
    """Send a report email via Resend API."""
    if runtime_config.get("notify_email") != "1":
        print("[EMAIL] Email notifications disabled — skipping.")
        return
    report_email = runtime_config.get("report_email") or ""
    if not report_email:
        print("[EMAIL] report_email not configured — skipping.")
        return
    _send(report_email, subject, body.replace("\n", "<br>"))
