"""
User management routes (admin CRUD) and email/phone verification.
"""
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify, render_template_string, redirect, url_for, session

import db
import config
from auth import require_login, require_role, current_user
from email_helper import send_verification_email

users_bp = Blueprint("users", __name__)


# ── Email verification (public) ───────────────────────────────────────────────

@users_bp.route("/verify-email/<token>")
def verify_email(token):
    # ── First-admin pending setup ──────────────────────────────────────────────
    pending = db.pending_setup_get_by_token(token)
    if pending:
        # Create the admin user now that email is confirmed
        roles = {r["name"]: r["id"] for r in db.roles_list()}
        admin_role_id = roles.get("admin")
        if admin_role_id:
            from werkzeug.security import generate_password_hash
            try:
                import sqlite3 as _sq
                import secrets as _sec
                db_path = __import__("pathlib").Path(__file__).parent.parent.parent / "data" / "app.db"
                con = _sq.connect(str(db_path))
                con.row_factory = _sq.Row
                cur = con.execute(
                    "INSERT INTO users (first_name, last_name, email, phone, password_hash, role_id, "
                    "email_verified, phone_verified, is_active) VALUES (?,?,?,?,?,?,1,0,0)",
                    (pending["first_name"], pending["last_name"], pending["email"],
                     pending["phone"], pending["password_hash"], admin_role_id),
                )
                con.commit()
                user_id = cur.lastrowid
                con.close()
            except Exception as e:
                print(f"[SETUP] Error creating admin user: {e}")
                return redirect(url_for("admin.setup"))
        db.pending_setup_clear()
        session["user_id"] = user_id
        return redirect(url_for("admin.admin"))

    # ── Normal user email verification ────────────────────────────────────────
    user = db.user_get_by_email_token(token)
    if not user:
        return render_template_string("""
        <!DOCTYPE html><html><head><title>Verification</title><meta charset="UTF-8">
        <style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
        min-height:100vh;margin:0;background:#f3f4f6;}
        .card{background:#fff;padding:40px;border-radius:12px;text-align:center;
        box-shadow:0 2px 20px rgba(0,0,0,.1);}</style></head>
        <body><div class="card">
        <div style="font-size:48px;margin-bottom:16px;">❌</div>
        <h2 style="color:#1f2937;">Invalid or expired link</h2>
        <p style="color:#6b7280;">This verification link is not valid or has already been used.</p>
        </div></body></html>"""), 400

    db.user_set_email_verified(user["id"])
    session["user_id"] = user["id"]
    return redirect(url_for("admin.admin"))


# ── Self-serve phone verification (any logged-in user for their own account) ──

@users_bp.route("/admin/api/my/send-phone-code", methods=["POST"])
@require_login
def api_my_send_phone_code():
    user = current_user()
    phone = user.get("phone", "").strip()
    if not phone:
        return jsonify({"error": "No phone number on your account"}), 400
    return _send_phone_code(user["id"], phone)


@users_bp.route("/admin/api/my/check-phone-code", methods=["POST"])
@require_login
def api_my_check_phone_code():
    user = current_user()
    code = (request.json or {}).get("code", "").strip()
    if not code:
        return jsonify({"error": "code required"}), 400
    return _check_phone_code(user["id"], user.get("phone", ""), code)


# ── User API (admin only) ─────────────────────────────────────────────────────

@users_bp.route("/admin/api/users", methods=["GET"])
@require_role("admin")
def api_users_list():
    users = db.user_list()
    for u in users:
        u["use_cases"] = db.user_get_use_cases(u["id"])
    return jsonify(users)


@users_bp.route("/admin/api/users", methods=["POST"])
@require_role("admin")
def api_users_create():
    me = current_user()
    if not me["phone_verified"]:
        return jsonify({"error": "Verify your own phone number before inviting others"}), 403

    data       = request.json or {}
    first_name = data.get("first_name", "").strip()
    last_name  = data.get("last_name",  "").strip()
    email      = data.get("email",      "").strip()
    phone      = data.get("phone",      "").strip()
    password   = data.get("password",   "").strip()
    role_name  = data.get("role",       "standard")
    uc_ids     = data.get("use_cases",  [])

    if not first_name or not last_name or not email or not password:
        return jsonify({"error": "first_name, last_name, email and password are required"}), 400

    roles = {r["name"]: r["id"] for r in db.roles_list()}
    role_id = roles.get(role_name)
    if not role_id:
        return jsonify({"error": f"Unknown role: {role_name}"}), 400

    if role_name == "manager" and not uc_ids:
        return jsonify({"error": "Managers must be assigned at least one use case"}), 400

    try:
        user_id = db.user_create(first_name, last_name, email, phone, password, role_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    if uc_ids:
        db.user_assign_use_cases(user_id, uc_ids)

    token = _get_email_token(user_id)
    if token:
        base_url = request.url_root.rstrip("/")
        send_verification_email(email, f"{base_url}/verify-email/{token}", first_name)

    return jsonify({"ok": True, "id": user_id}), 201


@users_bp.route("/admin/api/users/<int:user_id>", methods=["PATCH"])
@require_role("admin")
def api_users_update(user_id):
    data = request.json or {}
    uc_ids = data.pop("use_cases", None)

    role_name = data.pop("role", None)
    if role_name:
        roles = {r["name"]: r["id"] for r in db.roles_list()}
        role_id = roles.get(role_name)
        if not role_id:
            return jsonify({"error": f"Unknown role: {role_name}"}), 400
        data["role_id"] = role_id

    db.user_update(user_id, data)

    if uc_ids is not None:
        db.user_assign_use_cases(user_id, uc_ids)

    return jsonify({"ok": True})


@users_bp.route("/admin/api/users/<int:user_id>", methods=["DELETE"])
@require_role("admin")
def api_users_delete(user_id):
    me = current_user()
    if me and me["id"] == user_id:
        return jsonify({"error": "Cannot delete your own account"}), 400
    db.user_delete(user_id)
    return jsonify({"ok": True})


@users_bp.route("/admin/api/users/<int:user_id>/resend-verification", methods=["POST"])
@require_role("admin")
def api_users_resend_verification(user_id):
    user = db.user_get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    token = _get_email_token(user_id)
    if not token:
        return jsonify({"error": "No pending email token"}), 400
    base_url = request.url_root.rstrip("/")
    send_verification_email(user["email"], f"{base_url}/verify-email/{token}", user["first_name"])
    return jsonify({"ok": True})


@users_bp.route("/admin/api/users/<int:user_id>/send-phone-code", methods=["POST"])
@require_role("admin")
def api_send_phone_code(user_id):
    user = db.user_get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    return _send_phone_code(user_id, user.get("phone", ""))


@users_bp.route("/admin/api/users/<int:user_id>/check-phone-code", methods=["POST"])
@require_role("admin")
def api_check_phone_code(user_id):
    user = db.user_get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    code = (request.json or {}).get("code", "").strip()
    if not code:
        return jsonify({"error": "code required"}), 400
    return _check_phone_code(user_id, user.get("phone", ""), code)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _send_phone_code(user_id: int, phone: str):
    if not phone:
        return jsonify({"error": "No phone number on account"}), 400
    verify_sid = config.twilio_verify_sid()
    if not verify_sid:
        return jsonify({"error": "twilio_verify_sid not configured"}), 500
    try:
        client = config.twilio_client()
        client.verify.v2.services(verify_sid).verifications.create(to=phone, channel="sms")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _check_phone_code(user_id: int, phone: str, code: str):
    verify_sid = config.twilio_verify_sid()
    if not verify_sid:
        return jsonify({"error": "twilio_verify_sid not configured"}), 500
    if not phone:
        return jsonify({"error": "No phone number on account"}), 400
    try:
        client = config.twilio_client()
        check = client.verify.v2.services(verify_sid).verification_checks.create(
            to=phone, code=code
        )
        if check.status == "approved":
            db.user_set_phone_verified(user_id)
            updated = db.user_get(user_id)
            return jsonify({"ok": True, "is_active": updated["is_active"]})
        return jsonify({"error": "Invalid or expired code"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _get_email_token(user_id: int):
    db_path = Path(__file__).parent.parent.parent / "data" / "app.db"
    con = __import__("sqlite3").connect(str(db_path))
    con.row_factory = __import__("sqlite3").Row
    row = con.execute("SELECT email_token FROM users WHERE id = ?", (user_id,)).fetchone()
    con.close()
    return row["email_token"] if row else None
