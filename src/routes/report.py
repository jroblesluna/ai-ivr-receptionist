import os
from flask import Blueprint, render_template, abort, send_file, request
import reports
import runtime_config

report_bp = Blueprint("report", __name__)

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
        elevenlabs_voice_id=runtime_config.get("elevenlabs_voice_id"),
        tts_text=tts_text,
    )


@report_bp.route("/report/<report_id>/audio", methods=["GET"])
def report_audio_get(report_id):
    if not reports.load(report_id):
        abort(404)
    mp3 = reports.audio_path(report_id)
    if not mp3.exists():
        abort(404)
    return send_file(str(mp3), mimetype="audio/mpeg")


@report_bp.route("/report/<report_id>/audio", methods=["POST"])
def report_audio_post(report_id):
    if not reports.load(report_id):
        abort(404)
    mp3 = reports.audio_path(report_id)
    mp3.parent.mkdir(parents=True, exist_ok=True)
    mp3.write_bytes(request.get_data())
    return "", 204
