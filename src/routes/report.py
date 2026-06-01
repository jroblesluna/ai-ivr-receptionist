import os
from flask import Blueprint, render_template, abort, request, redirect
import reports
import runtime_config
from storage import storage, StorageDownloadError

report_bp = Blueprint("report", __name__)


@report_bp.route("/report/<report_id>")
def view_report(report_id):
    try:
        data = reports.load(report_id)
    except StorageDownloadError:
        abort(503)
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
        has_recording=True,
    )


@report_bp.route("/report/<report_id>/recording", methods=["GET"])
def report_recording(report_id):
    try:
        data = reports.load(report_id)
    except StorageDownloadError:
        abort(503)
    if not data:
        abort(404)
    url = reports.get_audio_url(report_id, suffix=".recording.mp3")
    return redirect(url)


@report_bp.route("/report/<report_id>/audio", methods=["GET"])
def report_audio_get(report_id):
    try:
        data = reports.load(report_id)
    except StorageDownloadError:
        abort(503)
    if not data:
        abort(404)
    url = reports.get_audio_url(report_id, suffix=".mp3")
    return redirect(url)


@report_bp.route("/report/<report_id>/audio", methods=["POST"])
def report_audio_post(report_id):
    try:
        data = reports.load(report_id)
    except StorageDownloadError:
        abort(503)
    if not data:
        abort(404)
    reports.save_audio(report_id, request.get_data(), suffix=".mp3")
    return "", 204
