"""
User management routes (admin-only CRUD) and email verification (public).
"""
import os
from flask import Blueprint, request, jsonify, render_template_string, redirect, url_for

import db
from auth import require_login, require_role, current_user
from email_helper import send_verification_email

users_bp = Blueprint("users", __name__)


# ── Email verification (public) ───────────────────────────────────────────────

@users_bp.route("/verify-email/<token>")
def verify_email(token):
    user = db.user_get_by_email_token(token)
    if not user:
        return render_template_string("""
        <!DOCTYPE html><html><head><title>Verification</title>
        <meta charset="UTF-8">
        <style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f3f4f6;}
        .card{background:#fff;padding:40px;border-radius:12px;text-align:center;box-shadow:0 2px 20px rgba(0,0,0,.1);}</style>
        </head><body><div class="card">
        <div style="font-size:48px;margin-bottom:16px;">❌</div>
        <h2 style="color:#1f2937;">Invalid or expired link</h2>
        <p style="color:#6b7280;">This verification link is not valid. Please contact an administrator.</p>
        </div></body></html>
        """), 400

    db.user_set_email_verified(user["id"])
    return render_template_string("""
    <!DOCTYPE html><html><head><title>Email Verified</title>
    <meta charset="UTF-8">
    <style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f3f4f6;}
    .card{background:#fff;padding:40px;border-radius:12px;text-align:center;box-shadow:0 2px 20px rgba(0,0,0,.1);}</style>
    </head><body><div class="card">
    <div style="font-size:48px;margin-bottom:16px;">✅</div>
    <h2 style="color:#1f2937;">Email verified!</h2>
    <p style="color:#6b7280;">Your email has been confirmed. You still need to verify your phone number to activate your account.</p>
    <p style="margin-top:20px;"><a href="/admin/login" style="color:#4f46e5;font-weight:600;text-decoration:none;">Go to Login →</a></p>
    </div></body></html>
    """)


# ── User API (admin only) ─────────────────────────────────────────────────────

@users_bp.route("/admin/api/users", methods=["GET"])
@require_role("admin")
def api_users_list():
    users = db.user_list()
    # Attach use-case assignments
    for u in users:
        u["use_cases"] = db.user_get_use_cases(u["id"])
    return jsonify(users)


@users_bp.route("/admin/api/users", methods=["POST"])
@require_role("admin")
def api_users_create():
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

    # Send verification email
    user = db.user_get(user_id)
    token = _get_email_token(user_id)
    if token:
        base_url = request.url_root.rstrip("/")
        verify_url = f"{base_url}/verify-email/{token}"
        send_verification_email(email, verify_url, first_name)

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
    verify_url = f"{base_url}/verify-email/{token}"
    send_verification_email(user["email"], verify_url, user["first_name"])
    return jsonify({"ok": True})


@users_bp.route("/admin/api/users/<int:user_id>/send-phone-code", methods=["POST"])
@require_role("admin")
def api_send_phone_code(user_id):
    from config import TWILIO_VERIFY_SID, ACCOUNT_SID, AUTH_TOKEN
    from twilio.rest import Client

    user = db.user_get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    phone = user.get("phone", "").strip()
    if not phone:
        return jsonify({"error": "User has no phone number"}), 400
    if not TWILIO_VERIFY_SID:
        return jsonify({"error": "TWILIO_VERIFY_SID not configured"}), 500

    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        client.verify.v2.services(TWILIO_VERIFY_SID).verifications.create(
            to=phone, channel="sms"
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@users_bp.route("/admin/api/users/<int:user_id>/check-phone-code", methods=["POST"])
@require_role("admin")
def api_check_phone_code(user_id):
    from config import TWILIO_VERIFY_SID, ACCOUNT_SID, AUTH_TOKEN
    from twilio.rest import Client

    user = db.user_get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404

    code = (request.json or {}).get("code", "").strip()
    if not code:
        return jsonify({"error": "code required"}), 400
    if not TWILIO_VERIFY_SID:
        return jsonify({"error": "TWILIO_VERIFY_SID not configured"}), 500

    phone = user.get("phone", "").strip()
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        check = client.verify.v2.services(TWILIO_VERIFY_SID).verification_checks.create(
            to=phone, code=code
        )
        if check.status == "approved":
            db.user_set_phone_verified(user_id)
            updated = db.user_get(user_id)
            return jsonify({"ok": True, "is_active": updated["is_active"]})
        else:
            return jsonify({"error": "Invalid or expired code"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _get_email_token(user_id: int) -> str | None:
    """Read the email_token directly from DB (not exposed in user dict)."""
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent.parent / "data" / "app.db"
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT email_token FROM users WHERE id = ?", (user_id,)).fetchone()
    con.close()
    return row["email_token"] if row else None
