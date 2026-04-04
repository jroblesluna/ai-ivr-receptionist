import os
import requests as req
from flask import Blueprint, render_template, abort, send_file
import reports
import runtime_config

report_bp = Blueprint("report", __name__)

_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — multilingual, clear


@report_bp.route("/report/<report_id>")
def view_report(report_id):
    data = reports.load(report_id)
    if not data:
        abort(404)
    return render_template("report.html", r=data)


@report_bp.route("/report/<report_id>/audio")
def report_audio(report_id):
    data = reports.load(report_id)
    if not data:
        abort(404)

    mp3 = reports.audio_path(report_id)

    if not mp3.exists():
        api_key  = os.environ.get("ELEVENLABS_API_KEY", "")
        voice_id = runtime_config.get("elevenlabs_voice_id") or _DEFAULT_VOICE_ID
        if not api_key:
            abort(503, description="ELEVENLABS_API_KEY not configured")

        lang    = data.get("language", "English")
        caller  = data.get("caller_name") or "Unknown"
        topic   = data.get("topic", "")
        summary = data.get("summary", "")

        if lang == "English":
            text = f"Call report for {caller}. Topic: {topic}. {summary}"
        else:
            text = f"Reporte de llamada para {caller}. Tema: {topic}. {summary}"

        resp = req.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=30,
        )
        if not resp.ok:
            abort(502, description=f"ElevenLabs error: {resp.text}")

        mp3.parent.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(resp.content)

    return send_file(str(mp3), mimetype="audio/mpeg")
