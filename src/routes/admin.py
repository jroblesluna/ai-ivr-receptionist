import json
import os
import db
from flask import Blueprint, request, session, redirect, url_for, render_template, jsonify
from config import ADMIN_PASSWORD
from use_case_loader import _load_use_cases, save_use_case
from whitelist import load_whitelist, add_number, remove_number
import runtime_config

admin_bp = Blueprint("admin", __name__)


def _logged_in():
    return session.get("admin") is True


@admin_bp.route("/admin")
def admin():
    if not _logged_in():
        return redirect(url_for("admin.login"))
    use_cases = _load_use_cases()
    base_url = request.url_root.rstrip("/")
    current_use_case = runtime_config.get("use_case_id")
    if not current_use_case or current_use_case not in use_cases:
        current_use_case = next(iter(use_cases), None)
        if current_use_case:
            runtime_config.set("use_case_id", current_use_case)
    return render_template(
        "admin.html",
        use_cases=use_cases,
        current_use_case=current_use_case,
        twilio_from=runtime_config.get("twilio_from"),
        forward_to=runtime_config.get("forward_to"),
        report_email=runtime_config.get("report_email"),
        whatsapp_from=runtime_config.get("whatsapp_from"),
        whatsapp_to=runtime_config.get("whatsapp_to"),
        notify_email=runtime_config.get("notify_email", "1"),
        notify_whatsapp=runtime_config.get("notify_whatsapp", "1"),
        elevenlabs_voice_id=runtime_config.get("elevenlabs_voice_id"),
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
        whitelist=load_whitelist(),
        webhook_url=f"{base_url}/menu",
    )


@admin_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin.admin"))
        error = "Invalid password."
    return render_template("login.html", error=error)


@admin_bp.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.route("/admin/api/config", methods=["POST"])
def api_config():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    if "use_case_id" in data:
        use_cases = _load_use_cases()
        if data["use_case_id"] not in use_cases:
            return jsonify({"error": "Unknown use case"}), 400
        runtime_config.set("use_case_id", data["use_case_id"])
    for key in ("twilio_from", "forward_to", "report_email", "whatsapp_from", "whatsapp_to",
                "notify_email", "notify_whatsapp", "elevenlabs_voice_id"):
        if key in data:
            runtime_config.set(key, data[key])
    return jsonify({"ok": True, "config": runtime_config.all_config()})


@admin_bp.route("/admin/api/tts-preview", methods=["POST"])
def api_tts_preview():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    import os, requests as req
    api_key = os.environ.get("GOOGLE_TTS_API_KEY", "")
    if not api_key:
        return jsonify({"error": "GOOGLE_TTS_API_KEY not configured"}), 500
    data  = request.json or {}
    voice = data.get("voice", "")    # "Google.en-GB-Neural2-F"
    text  = data.get("text", "").strip()
    if not voice or not text:
        return jsonify({"error": "voice and text required"}), 400
    voice_name    = voice.replace("Google.", "")   # "en-GB-Neural2-F"
    language_code = voice_name[:5]                 # "en-GB"
    resp = req.post(
        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}",
        json={
            "input": {"text": text},
            "voice": {"languageCode": language_code, "name": voice_name},
            "audioConfig": {"audioEncoding": "MP3"},
        },
        timeout=10,
    )
    if not resp.ok:
        return jsonify({"error": resp.text}), 500
    return jsonify({"audio": resp.json().get("audioContent", "")})


@admin_bp.route("/admin/api/use-case", methods=["POST"])
def api_create_use_case():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    uc_id = data.get("id", "").strip()
    if not uc_id:
        return jsonify({"error": "id required"}), 400
    import db as _db
    if _db.uc_get(uc_id):
        return jsonify({"error": "Use case already exists"}), 409
    save_use_case(uc_id, data)
    return jsonify({"ok": True, "id": uc_id}), 201


@admin_bp.route("/admin/api/use-case/<uc_id>", methods=["PATCH"])
def api_update_use_case(uc_id):
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    use_cases = _load_use_cases()
    if uc_id not in use_cases:
        return jsonify({"error": "Not found"}), 404
    data = request.json or {}
    data["id"] = uc_id
    save_use_case(uc_id, data)
    return jsonify({"ok": True})


@admin_bp.route("/admin/api/use-case/<uc_id>", methods=["DELETE"])
def api_delete_use_case(uc_id):
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    import db as _db, runtime_config
    if runtime_config.get("use_case_id") == uc_id:
        return jsonify({"error": "Cannot delete active use case"}), 400
    _db.uc_delete(uc_id)
    return jsonify({"ok": True})


@admin_bp.route("/admin/api/elevenlabs-voices", methods=["GET"])
def api_elevenlabs_voices():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    import os, requests as req
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ELEVENLABS_API_KEY not configured"}), 500
    resp = req.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": api_key},
        timeout=10,
    )
    if not resp.ok:
        return jsonify({"error": resp.text}), 502
    voices = [
        {"voice_id": v["voice_id"], "name": v["name"], "category": v.get("category", "")}
        for v in resp.json().get("voices", [])
    ]
    voices.sort(key=lambda v: v["name"])
    return jsonify(voices)


@admin_bp.route("/admin/api/elevenlabs-preview", methods=["POST"])
def api_elevenlabs_preview():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    import os, base64, requests as req
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ELEVENLABS_API_KEY not configured"}), 500
    data     = request.json or {}
    voice_id = data.get("voice_id", "").strip()
    text     = data.get("text", "").strip()
    if not voice_id or not text:
        return jsonify({"error": "voice_id and text required"}), 400
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
        return jsonify({"error": resp.text}), 502
    return jsonify({"audio": base64.b64encode(resp.content).decode()})


@admin_bp.route("/admin/api/reports", methods=["GET"])
def api_reports():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    offset = int(request.args.get("offset", 0))
    rows   = db.report_list(limit=50, offset=offset)
    total  = db.report_count()
    return jsonify({"reports": rows, "total": total, "offset": offset})


@admin_bp.route("/admin/api/whitelist", methods=["GET"])
def api_whitelist_get():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(load_whitelist())


@admin_bp.route("/admin/api/whitelist", methods=["POST"])
def api_whitelist_add():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    phone = (request.json or {}).get("phone", "").strip()
    if not phone:
        return jsonify({"error": "Phone required"}), 400
    add_number(phone)
    return jsonify(load_whitelist())


@admin_bp.route("/admin/api/whitelist/<path:phone>", methods=["DELETE"])
def api_whitelist_remove(phone):
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    remove_number(phone)
    return jsonify(load_whitelist())


@admin_bp.route("/admin/api/reset", methods=["POST"])
def api_reset():
    if not _logged_in():
        return jsonify({"error": "Unauthorized"}), 401
    import shutil
    from pathlib import Path

    data_dir = Path(__file__).parent.parent.parent / "data"

    # Delete the database
    db_path = data_dir / "app.db"
    if db_path.exists():
        db_path.unlink()

    # Delete all report files
    reports_dir = data_dir / "reports"
    if reports_dir.exists():
        shutil.rmtree(reports_dir)

    # Re-initialize DB (creates tables + seeds from JSON files)
    db.init()
    db.migrate_config_from_json()
    db.migrate_use_cases_from_json()

    return jsonify({"ok": True})
