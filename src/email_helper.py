import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, REPORT_EMAIL


def send_report_email(subject: str, body: str) -> None:
    """Send a plain-text report email. Silently logs on failure."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("[EMAIL] SMTP credentials not configured — skipping email.")
        return

    msg = MIMEMultipart()
    msg["From"]    = SMTP_FROM
    msg["To"]      = REPORT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, REPORT_EMAIL, msg.as_string())
        print(f"[EMAIL] Report sent to {REPORT_EMAIL}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
