"""End-of-call processing for the real-time voice pipeline.

Handles report generation, WhatsApp notifications, and email reports when a
real-time voice call ends — either via LLM end_call=true or unexpected
disconnection. Mirrors the existing conversational agent flow in
src/routes/ai.py for consistency.

Requirements: 12.1, 12.2, 12.3, 12.4, 7.4, 7.6
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timezone helper (mirrors _now_local from src/routes/ai.py)
# ---------------------------------------------------------------------------


def _now_local() -> datetime:
    """Get current time in the configured timezone."""
    import sys
    import os

    # Ensure src/ is on the path for bare imports used by runtime_config
    src_dir = os.path.join(os.path.dirname(__file__), "..")
    if src_dir not in sys.path:
        sys.path.insert(0, os.path.abspath(src_dir))

    import runtime_config

    tz_name = runtime_config.get("timezone", "America/Lima").replace(" ", "_")
    try:
        tz = ZoneInfo(tz_name)
        return datetime.now(tz)
    except Exception:
        return datetime.now(ZoneInfo("UTC"))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_call_report(
    *,
    call_sid: str,
    demo_id: str,
    language: str,
    caller_from: str,
    conversation_history: list[dict[str, Any]],
    collected_info: dict[str, Any],
    incomplete: bool = False,
) -> dict[str, Any]:
    """Build a call report dict in the same format as the existing conversational agent flow.

    The report contains: timestamp, use_case name, caller_name, caller_phone,
    topic, language, conversation (without system messages), and summary.

    Args:
        call_sid: The Twilio call SID.
        demo_id: The demo use case ID.
        language: The conversation language code (e.g. "en", "es").
        caller_from: The caller's phone number.
        conversation_history: Full conversation history including system messages.
        collected_info: Collected caller info from the session.
        incomplete: Whether the call ended unexpectedly (partial report).

    Returns:
        A report data dict ready to be passed to reports.save().
    """
    import src.db as db

    # Get use case name
    use_case_name = ""
    if demo_id:
        uc = db.uc_get(demo_id)
        if uc:
            use_case_name = uc.get("name", "")

    # Filter out system messages for the report conversation
    conv_history = [
        m for m in conversation_history if m.get("role") != "system"
    ]

    # Build report data matching the existing format
    report_data: dict[str, Any] = {
        "timestamp": _now_local().strftime("%Y-%m-%d %H:%M:%S"),
        "use_case": use_case_name,
        "caller_name": collected_info.get("name") or caller_from,
        "caller_phone": collected_info.get("phone") or caller_from,
        "topic": "Conversational Agent",
        "language": "English" if language == "en" else "Español",
        "conversation": conv_history,
        "operator_briefing": "",
        "transcription": "",
        "transcription_segments": [],
        "summary": collected_info.get("notes") or "",
        "goodbye": collected_info.get("goodbye") or "",
    }

    if incomplete:
        report_data["incomplete"] = True
        report_data["summary"] = (
            f"[INCOMPLETE - Unexpected disconnection] "
            f"{report_data['summary']}"
        )

    return report_data


def save_call_report(report_data: dict[str, Any]) -> str:
    """Persist the call report using the existing reports module.

    Args:
        report_data: The report dict from generate_call_report().

    Returns:
        The report ID.
    """
    import sys
    import os

    # Ensure src/ is on the path for bare imports used by reports.py
    src_dir = os.path.join(os.path.dirname(__file__), "..")
    if src_dir not in sys.path:
        sys.path.insert(0, os.path.abspath(src_dir))

    import reports

    report_id = reports.save(report_data)
    logger.info(
        "Call report saved",
        extra={
            "report_id": report_id,
            "caller_name": report_data.get("caller_name"),
            "incomplete": report_data.get("incomplete", False),
        },
    )
    return report_id


# ---------------------------------------------------------------------------
# Notifications (WhatsApp + Email)
# ---------------------------------------------------------------------------


def send_whatsapp_notification(
    *,
    report_data: dict[str, Any],
    report_id: str,
    base_url: str = "",
) -> None:
    """Send WhatsApp notification using the same conditions as the existing system.

    Only sends if notify_whatsapp is enabled and whatsapp_from/whatsapp_to are configured.

    Args:
        report_data: The call report data dict.
        report_id: The saved report ID.
        base_url: The base URL for report links (optional).
    """
    import sys
    import os

    # Ensure src/ is on the path for bare imports used by runtime_config
    src_dir = os.path.join(os.path.dirname(__file__), "..")
    if src_dir not in sys.path:
        sys.path.insert(0, os.path.abspath(src_dir))

    import runtime_config
    from config import twilio_client

    if runtime_config.get("notify_whatsapp") != "1":
        logger.debug("WhatsApp notifications disabled — skipping")
        return

    wa_from = runtime_config.get("whatsapp_from") or ""
    wa_to = runtime_config.get("whatsapp_to") or ""

    if not wa_from or not wa_to:
        logger.debug("WhatsApp from/to not configured — skipping")
        return

    report_url = f"{base_url}/report/{report_id}" if base_url else ""

    lines = [
        f"📋 *Call Report* — {report_data.get('timestamp', '')}",
        f"🏢 {report_data.get('use_case', '')}",
        f"📌 Tema: {report_data.get('topic', '')}",
        f"🌐 Idioma: {report_data.get('language', '')}",
        f"👤 Nombre: {report_data.get('caller_name', '')}",
        f"📞 Teléfono: {report_data.get('caller_phone', '')}",
    ]

    summary = report_data.get("summary", "")
    if summary:
        lines.append(f"📝 Resumen: {summary}")

    if report_data.get("incomplete"):
        lines.append("⚠️ Llamada incompleta (desconexión inesperada)")

    if report_url:
        lines.append(f"\n🔗 {report_url}")

    try:
        msg = twilio_client().messages.create(
            from_=f"whatsapp:{wa_from}",
            to=f"whatsapp:{wa_to}",
            body="\n".join(lines),
        )
        logger.info(
            "WhatsApp notification sent",
            extra={"wa_to": wa_to, "message_sid": msg.sid},
        )
    except Exception as exc:
        logger.error(
            "Failed to send WhatsApp notification",
            extra={"error": str(exc), "wa_to": wa_to},
        )


def send_email_report(
    *,
    report_data: dict[str, Any],
    report_id: str,
    base_url: str = "",
) -> None:
    """Send email report using the same conditions as the existing system.

    Only sends if notify_email is enabled and report_email is configured.

    Args:
        report_data: The call report data dict.
        report_id: The saved report ID.
        base_url: The base URL for report links (optional).
    """
    import sys
    import os

    # Ensure src/ is on the path for bare imports used by email_helper
    src_dir = os.path.join(os.path.dirname(__file__), "..")
    if src_dir not in sys.path:
        sys.path.insert(0, os.path.abspath(src_dir))

    from email_helper import send_report_email

    report_url = f"{base_url}/report/{report_id}" if base_url else ""

    caller_from = report_data.get("caller_phone", "unknown")
    subject = f"[IVR] Call Report — {caller_from}"

    body_lines = [
        f"CALL REPORT — {report_data.get('timestamp', '')}",
        f"Use Case  : {report_data.get('use_case', '')}",
        f"Caller    : {report_data.get('caller_name', '')} / {report_data.get('caller_phone', '')}",
        f"Topic     : {report_data.get('topic', '')}",
        f"Language  : {report_data.get('language', '')}",
        f"Summary   : {report_data.get('summary', '')}",
    ]

    if report_data.get("incomplete"):
        body_lines.append("Status    : INCOMPLETE (unexpected disconnection)")

    if report_url:
        body_lines.append(f"")
        body_lines.append(f"View report: {report_url}")

    send_report_email(subject=subject, body="\n".join(body_lines))


# ---------------------------------------------------------------------------
# End-of-call orchestration
# ---------------------------------------------------------------------------


def process_end_of_call(
    *,
    call_sid: str,
    demo_id: str,
    language: str,
    caller_from: str,
    conversation_history: list[dict[str, Any]],
    collected_info: dict[str, Any],
    incomplete: bool = False,
    base_url: str = "",
) -> str | None:
    """Full end-of-call processing: generate report, send notifications.

    This is the main entry point called when a real-time voice call ends.
    It mirrors the end-of-call logic in the existing ai_respond route for
    conversational agents.

    Args:
        call_sid: The Twilio call SID.
        demo_id: The demo use case ID.
        language: The conversation language code.
        caller_from: The caller's phone number.
        conversation_history: Full conversation history.
        collected_info: Collected caller info from the session.
        incomplete: Whether the call ended unexpectedly.
        base_url: The base URL for report links.

    Returns:
        The report ID if saved successfully, None on failure.
    """
    try:
        # Generate the report
        report_data = generate_call_report(
            call_sid=call_sid,
            demo_id=demo_id,
            language=language,
            caller_from=caller_from,
            conversation_history=conversation_history,
            collected_info=collected_info,
            incomplete=incomplete,
        )

        # Save the report
        report_id = save_call_report(report_data)

        # Send notifications
        send_whatsapp_notification(
            report_data=report_data,
            report_id=report_id,
            base_url=base_url,
        )
        send_email_report(
            report_data=report_data,
            report_id=report_id,
            base_url=base_url,
        )

        logger.info(
            "End-of-call processing complete",
            extra={
                "call_sid": call_sid,
                "report_id": report_id,
                "incomplete": incomplete,
            },
        )
        return report_id

    except Exception as exc:
        logger.error(
            "End-of-call processing failed",
            extra={
                "call_sid": call_sid,
                "error": str(exc),
                "incomplete": incomplete,
            },
        )
        return None
