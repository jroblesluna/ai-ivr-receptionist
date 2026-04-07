import requests
import runtime_config
import config


def _send(to_email: str, subject: str, html: str, api_key: str = "", from_addr: str = "") -> tuple[bool, str]:
    """Send email via Resend. Returns (success, error_message)."""
    api_key   = api_key   or config.resend_api_key()
    from_addr = from_addr or config.resend_from_addr()
    if not api_key:
        return False, "Resend API key not configured."
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
            return True, ""
        msg = resp.json().get("message") or resp.text
        print(f"[EMAIL ERROR] Resend {resp.status_code}: {resp.text}")
        return False, f"Resend error {resp.status_code}: {msg}"
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False, str(e)


def send_verification_email(to_email: str, verify_url: str, first_name: str,
                             api_key: str = "") -> tuple[bool, str]:
    """Send verification email. Returns (success, error_message)."""
    html = (
        f"<p>Hi {first_name},</p>"
        f"<p>Please verify your email address by clicking the link below:</p>"
        f"<p><a href='{verify_url}' style='color:#4f46e5;font-weight:bold;'>Verify Email →</a></p>"
        f"<p>If you did not request this, you can ignore this email.</p>"
    )
    return _send(to_email, "Verify your email — IVR Admin", html, api_key=api_key)


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
