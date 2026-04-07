"""
Auth helpers: session management, login decorators, RBAC.
"""
from functools import wraps

from flask import session, redirect, url_for, jsonify, request

import db


def current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    return db.user_get(uid)


def _is_api():
    return request.path.startswith("/admin/api/") or request.is_json


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            if _is_api():
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """Decorator: user must be logged in AND have one of the given role names."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = current_user()
            if not user:
                if _is_api():
                    return jsonify({"error": "Unauthorized"}), 401
                return redirect(url_for("admin.login"))
            if user["role"] not in roles:
                if _is_api():
                    return jsonify({"error": "Forbidden"}), 403
                return redirect(url_for("admin.admin"))
            return f(*args, **kwargs)
        return decorated
    return decorator
