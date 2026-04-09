import os
import db
import config
from flask import Blueprint, request, session, redirect, url_for, render_template, jsonify
from use_case_loader import _load_use_cases, save_use_case
from whitelist import load_whitelist, add_number, remove_number
from auth import require_login, require_role, current_user
import runtime_config

admin_bp = Blueprint("admin", __name__)

# Keys stored encrypted in DB config table
_CREDENTIAL_KEYS = [
    "twilio_account_sid",
    "twilio_auth_token",
    "twilio_api_key_sid",
    "twilio_api_key_secret",
    "twilio_twiml_app_sid",
    "twilio_verify_sid",
    "openai_api_key",
    "resend_api_key",
    "resend_from",
    "elevenlabs_api_key",
    "google_tts_api_key",
]


# ── First-run setup ───────────────────────────────────────────────────────────

@admin_bp.route("/admin/setup", methods=["GET", "POST"])
def setup():
    if db.has_users():
        return redirect(url_for("admin.login"))
    error = None
    if request.method == "POST":
        import secrets as _sec
        from werkzeug.security import generate_password_hash
        from email_helper import send_verification_email

        first_name     = request.form.get("first_name",     "").strip()
        last_name      = request.form.get("last_name",      "").strip()
        email          = request.form.get("email",          "").strip()
        phone          = request.form.get("phone",          "").strip()
        password       = request.form.get("password",       "").strip()
        confirm        = request.form.get("confirm",        "").strip()
        resend_api_key = request.form.get("resend_api_key", "").strip()

        if not all([first_name, last_name, email, phone, password]):
            error = "All fields are required."
        elif password != confirm:
            error = "Passwords do not match."
        elif not resend_api_key:
            error = "A valid Resend API key is required to send the verification email."
        else:
            token      = _sec.token_urlsafe(32)
            base_url   = request.url_root.rstrip("/")
            verify_url = f"{base_url}/verify-email/{token}"

            # Try sending BEFORE persisting anything
            ok, send_error = send_verification_email(email, verify_url, first_name,
                                                     api_key=resend_api_key)
            if not ok:
                error = f"Could not send verification email: {send_error}"
            else:
                # Email sent — now persist pending setup and save the working key
                db.pending_setup_save({
                    "first_name":    first_name,
                    "last_name":     last_name,
                    "email":         email.lower(),
                    "phone":         phone,
                    "password_hash": generate_password_hash(password),
                    "token":         token,
                })
                db.config_set_secure("resend_api_key", resend_api_key)
                return render_template("setup_pending.html", email=email)

    return render_template("setup.html", error=error)


# ── Main admin ────────────────────────────────────────────────────────────────

@admin_bp.route("/admin")
@require_login
def admin():
    # Redirect to setup if no users exist (fresh install)
    if not db.has_users():
        return redirect(url_for("admin.setup"))
    user = current_user()
    use_cases = _load_use_cases()
    base_url = request.url_root.rstrip("/")
    current_use_case = runtime_config.get("use_case_id")
    if not current_use_case or current_use_case not in use_cases:
        current_use_case = next(iter(use_cases), None)
        if current_use_case:
            runtime_config.set("use_case_id", current_use_case)
    # For non-admins, fetch the user's assigned use cases (None = all access)
    user_use_cases = db.user_get_use_cases(user["id"]) if user and user["role"] != "admin" else None
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
        elevenlabs_api_key=config.elevenlabs_api_key(),
        whitelist=load_whitelist(),
        webhook_url=f"{base_url}/menu",
        user_role=user["role"] if user else "",
        user_name=f"{user['first_name']} {user['last_name']}" if user else "",
        phone_verified=user["phone_verified"] if user else False,
        current_user_id=user["id"] if user else None,
        current_user_phone=user["phone"] if user else "",
        user_use_cases=user_use_cases,
    )


@admin_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    # Redirect to setup if no users yet
    if not db.has_users():
        return redirect(url_for("admin.setup"))
    if current_user():
        return redirect(url_for("admin.admin"))
    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        user = db.user_check_password(email, password)
        if user and user["email_verified"]:
            session["user_id"] = user["id"]
            return redirect(url_for("admin.admin"))
        elif user and not user["email_verified"]:
            error = "Please verify your email first — check your inbox."
        else:
            error = "Invalid email or password."
    use_cases = _load_use_cases()
    current_use_case_id = runtime_config.get("use_case_id")
    active_uc_name = use_cases.get(current_use_case_id, {}).get("name", "") if current_use_case_id else ""
    return render_template("login.html", error=error, active_uc_name=active_uc_name)


@admin_bp.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ── Config ────────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/api/config", methods=["POST"])
@require_login
def api_config():
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


# ── Credentials (admin only) ──────────────────────────────────────────────────

@admin_bp.route("/admin/api/credentials", methods=["GET"])
@require_role("admin")
def api_credentials_get():
    """Return actual decrypted credential values (admin only)."""
    result = {}
    for key in _CREDENTIAL_KEYS:
        result[key] = db.config_get_secure(key) or ""
    return jsonify(result)


@admin_bp.route("/admin/api/credentials", methods=["POST"])
@require_role("admin")
def api_credentials_set():
    """Save credentials encrypted in DB. Only non-empty values are updated."""
    data = request.json or {}
    saved = []
    for key in _CREDENTIAL_KEYS:
        val = data.get(key, "").strip()
        if val:
            db.config_set_secure(key, val)
            saved.append(key)
    return jsonify({"ok": True, "saved": saved})


# ── TTS preview ───────────────────────────────────────────────────────────────

@admin_bp.route("/admin/api/tts-preview", methods=["POST"])
@require_login
def api_tts_preview():
    import requests as req
    api_key = config.google_tts_api_key()
    if not api_key:
        return jsonify({"error": "google_tts_api_key not configured"}), 500
    data  = request.json or {}
    voice = data.get("voice", "")
    text  = data.get("text", "").strip()
    if not voice or not text:
        return jsonify({"error": "voice and text required"}), 400
    voice_name    = voice.replace("Google.", "")
    language_code = voice_name[:5]
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


# ── Use Case CRUD ─────────────────────────────────────────────────────────────

@admin_bp.route("/admin/api/use-case", methods=["POST"])
@require_role("admin")
def api_create_use_case():
    data = request.json or {}
    uc_id = data.get("id", "").strip()
    if not uc_id:
        return jsonify({"error": "id required"}), 400
    if db.uc_get(uc_id):
        return jsonify({"error": "Use case already exists"}), 409
    save_use_case(uc_id, data)
    return jsonify({"ok": True, "id": uc_id}), 201


@admin_bp.route("/admin/api/use-case/<uc_id>", methods=["PATCH"])
@require_role("admin")
def api_update_use_case(uc_id):
    use_cases = _load_use_cases()
    if uc_id not in use_cases:
        return jsonify({"error": "Not found"}), 404
    data = request.json or {}
    data["id"] = uc_id
    save_use_case(uc_id, data)
    return jsonify({"ok": True})


@admin_bp.route("/admin/api/use-case/<uc_id>", methods=["DELETE"])
@require_role("admin")
def api_delete_use_case(uc_id):
    if runtime_config.get("use_case_id") == uc_id:
        return jsonify({"error": "Cannot delete active use case"}), 400
    db.uc_delete(uc_id)
    return jsonify({"ok": True})


# ── ElevenLabs ────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/api/elevenlabs-voices", methods=["GET"])
@require_login
def api_elevenlabs_voices():
    import requests as req
    api_key = config.elevenlabs_api_key()
    if not api_key:
        return jsonify({"error": "elevenlabs_api_key not configured"}), 500
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
@require_login
def api_elevenlabs_preview():
    import base64, requests as req
    api_key = config.elevenlabs_api_key()
    if not api_key:
        return jsonify({"error": "elevenlabs_api_key not configured"}), 500
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


# ── Reports ───────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/api/reports", methods=["GET"])
@require_login
def api_reports():
    offset = int(request.args.get("offset", 0))
    rows   = db.report_list(limit=50, offset=offset)
    total  = db.report_count()
    return jsonify({"reports": rows, "total": total, "offset": offset})


# ── Whitelist ─────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/api/whitelist", methods=["GET"])
@require_login
def api_whitelist_get():
    return jsonify(load_whitelist())


@admin_bp.route("/admin/api/whitelist", methods=["POST"])
@require_login
def api_whitelist_add():
    phone = (request.json or {}).get("phone", "").strip()
    if not phone:
        return jsonify({"error": "Phone required"}), 400
    add_number(phone)
    return jsonify(load_whitelist())


@admin_bp.route("/admin/api/whitelist/<path:phone>", methods=["DELETE"])
@require_login
def api_whitelist_remove(phone):
    remove_number(phone)
    return jsonify(load_whitelist())


# ── Test Call ─────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/test-call")
def test_call_page():
    return render_template("test_call.html")


@admin_bp.route("/admin/api/test-call-token", methods=["GET"])
def api_test_call_token():
    from twilio.jwt.access_token import AccessToken
    from twilio.jwt.access_token.grants import VoiceGrant
    api_key_sid    = config.twilio_api_key_sid()
    api_key_secret = config.twilio_api_key_secret()
    twiml_app_sid  = config.twilio_twiml_app_sid()
    if not api_key_sid or not api_key_secret or not twiml_app_sid:
        return jsonify({"error": "twilio_api_key_sid / twilio_api_key_secret / twilio_twiml_app_sid not configured"}), 500
    token = AccessToken(config.account_sid(), api_key_sid, api_key_secret,
                        identity="admin_test", ttl=3600)
    grant = VoiceGrant(outgoing_application_sid=twiml_app_sid, incoming_allow=False)
    token.add_grant(grant)
    return jsonify({
        "token": token.to_jwt(),
        "caller_id": runtime_config.get("twilio_from") or "",
    })


# ── Reset ─────────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/api/reset", methods=["POST"])
@require_role("admin")
def api_reset():
    import shutil
    from pathlib import Path

    data_dir = Path(__file__).parent.parent.parent / "data"

    db_path = data_dir / "app.db"
    if db_path.exists():
        db_path.unlink()

    reports_dir = data_dir / "reports"
    if reports_dir.exists():
        shutil.rmtree(reports_dir)

    db.init()
    db.migrate_config_from_json()
    db.migrate_use_cases_from_json()
    db.seed_roles_and_admin()

    return jsonify({"ok": True})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_email_token(user_id: int) -> str | None:
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent.parent / "data" / "app.db"
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT email_token FROM users WHERE id = ?", (user_id,)).fetchone()
    con.close()
    return row["email_token"] if row else None
