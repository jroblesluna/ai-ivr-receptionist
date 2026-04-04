import os
from flask import Blueprint, render_template, abort
import reports
import runtime_config

report_bp = Blueprint("report", __name__)

_DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"


@report_bp.route("/report/<report_id>")
def view_report(report_id):
    data = reports.load(report_id)
    if not data:
        abort(404)

    lang    = data.get("language", "English")
    caller  = data.get("caller_name") or "Unknown"
    topic   = data.get("topic", "")
    summary = data.get("summary", "")

    if lang == "English":
        tts_text = f"Call report for {caller}. Topic: {topic}. {summary}"
    else:
        tts_text = f"Reporte de llamada para {caller}. Tema: {topic}. {summary}"

    return render_template(
        "report.html",
        r=data,
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
        elevenlabs_voice_id=runtime_config.get("elevenlabs_voice_id") or _DEFAULT_VOICE_ID,
        tts_text=tts_text,
    )
