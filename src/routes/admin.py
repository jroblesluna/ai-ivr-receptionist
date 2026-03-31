import json
from flask import Blueprint, request, session, redirect, url_for, render_template, jsonify
from config import ADMIN_PASSWORD
from use_case_loader import _load_use_cases
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
    return render_template(
        "admin.html",
        use_cases=use_cases,
        current_use_case=runtime_config.get("use_case_id"),
        forward_to=runtime_config.get("forward_to"),
        whitelist=load_whitelist(),
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
    if "forward_to" in data:
        runtime_config.set("forward_to", data["forward_to"])
    return jsonify({"ok": True, "config": runtime_config.all_config()})


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
