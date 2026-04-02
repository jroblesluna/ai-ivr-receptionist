import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
import runtime_config


def send_report_email(subject: str, body: str) -> None:
    """Send a plain-text report email. Silently logs on failure."""
    if runtime_config.get("notify_email") != "1":
        print("[EMAIL] Email notifications disabled — skipping.")
        return
    if not SMTP_USER or not SMTP_PASSWORD:
        print("[EMAIL] SMTP credentials not configured — skipping email.")
        return

    report_email = runtime_config.get("report_email") or ""
    if not report_email:
        print("[EMAIL] REPORT_EMAIL not configured — skipping email.")
        return

    msg = MIMEMultipart()
    msg["From"]    = SMTP_FROM
    msg["To"]      = report_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, report_email, msg.as_string())
        print(f"[EMAIL] Report sent to {report_email}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
