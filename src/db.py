"""
SQLite storage for call reports index and runtime configuration.
DB file: data/app.db (persisted via Railway Volume at /app/data)
"""
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash


# ── Fernet encryption (used for sensitive config values) ──────────────────────

def _fernet():
    from cryptography.fernet import Fernet
    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        raise RuntimeError("SECRET_KEY env var not set — cannot encrypt/decrypt credentials")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def config_set_secure(key: str, value: str):
    """Store a config value encrypted with SECRET_KEY."""
    encrypted = _fernet().encrypt(value.encode()).decode()
    config_set(f"_sec_{key}", encrypted)


def config_get_secure(key: str, default: str = "") -> str:
    """Read and decrypt a secure config value. Returns default if not set or on error."""
    raw = config_get(f"_sec_{key}")
    if not raw:
        return default
    try:
        return _fernet().decrypt(raw.encode()).decode()
    except Exception:
        return default

_DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
_lock = threading.Lock()


def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


# ── Config ────────────────────────────────────────────────────────────────────

def config_get(key: str, default=None):
    with _conn() as con:
        row = con.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def config_set(key: str, value: str):
    with _lock, _conn() as con:
        con.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
        con.commit()


def config_all() -> dict:
    with _conn() as con:
        rows = con.execute("SELECT key, value FROM config").fetchall()
    return {r["key"]: r["value"] for r in rows}


def config_seed(defaults: dict):
    """Insert keys that don't exist yet (used on first boot)."""
    with _lock, _conn() as con:
        for key, value in defaults.items():
            con.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                (key, value if value is not None else "")
            )
        con.commit()


# ── Reports ───────────────────────────────────────────────────────────────────

def report_insert(report_id: str, data: dict):
    with _lock, _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO reports "
            "(id, datetime, caller_number, caller_name, topic, language) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                report_id,
                data.get("timestamp", ""),
                data.get("caller_phone", ""),
                data.get("caller_name", ""),
                data.get("topic", ""),
                data.get("language", ""),
            ),
        )
        con.commit()


def report_list(limit: int = 50, offset: int = 0) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM reports ORDER BY datetime DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def report_count() -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM reports").fetchone()[0]


def migrate_reports_from_json():
    """Scan existing JSON report files and index any missing records."""
    reports_dir = Path(__file__).parent.parent / "data" / "reports"
    if not reports_dir.exists():
        return
    with _conn() as con:
        existing = {r[0] for r in con.execute("SELECT id FROM reports").fetchall()}
    for path in reports_dir.glob("*.json"):
        report_id = path.stem
        if report_id not in existing:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                report_insert(report_id, data)
            except Exception:
                pass


def migrate_config_from_json():
    """Seed config table from runtime_config_defaults.json (committed in src/).
    Falls back to data/runtime_config.json for backwards compatibility."""
    for json_path in [
        Path(__file__).parent / "runtime_config_defaults.json",
        Path(__file__).parent.parent / "data" / "runtime_config.json",
    ]:
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                config_seed(data)
            except Exception:
                pass
            return


# ── Use Cases ─────────────────────────────────────────────────────────────────

def _row_to_uc(row) -> dict:
    return {
        "id":         row["id"],
        "name":       row["name"],
        "industry":   row["industry"] or "",
        "url":        row["url"] or "",
        "forward_to": row["forward_to"] or "",
        "voice":      {"en": row["voice_en"] or "", "es": row["voice_es"] or ""},
        "slogan":     {"en": row["slogan_en"] or "", "es": row["slogan_es"] or ""},
        "topics":     {},
    }


def _row_to_topic(row) -> dict:
    return {
        "digit":        row["digit"] or "",
        "meeting_type": bool(row["meeting_type"]),
        "en": {
            "label":        row["label_en"] or "",
            "menu_text":    row["menu_text_en"] or "",
            "greeting":     row["greeting_en"] or "",
            "system_extra": row["system_extra_en"] or "",
            "questions":    json.loads(row["questions_en"] or "[]"),
        },
        "es": {
            "label":        row["label_es"] or "",
            "menu_text":    row["menu_text_es"] or "",
            "greeting":     row["greeting_es"] or "",
            "system_extra": row["system_extra_es"] or "",
            "questions":    json.loads(row["questions_es"] or "[]"),
        },
    }


def uc_list() -> dict:
    """Return all use cases with their topics as {id: uc_dict}."""
    with _conn() as con:
        uc_rows = con.execute("SELECT * FROM use_cases ORDER BY name").fetchall()
        topic_rows = con.execute(
            "SELECT * FROM topics ORDER BY use_case_id, digit"
        ).fetchall()
    result = {}
    for r in uc_rows:
        uc = _row_to_uc(r)
        result[uc["id"]] = uc
    for r in topic_rows:
        uc_id = r["use_case_id"]
        if uc_id in result:
            result[uc_id]["topics"][r["key"]] = _row_to_topic(r)
    return result


def uc_get(uc_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM use_cases WHERE id = ?", (uc_id,)).fetchone()
        if not row:
            return None
        uc = _row_to_uc(row)
        topic_rows = con.execute(
            "SELECT * FROM topics WHERE use_case_id = ? ORDER BY digit",
            (uc_id,)
        ).fetchall()
    for r in topic_rows:
        uc["topics"][r["key"]] = _row_to_topic(r)
    return uc


def uc_upsert(uc_id: str, data: dict):
    """Save/update a use case and all its topics atomically."""
    v  = data.get("voice", {})
    sl = data.get("slogan", {})
    with _lock, _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO use_cases "
            "(id, name, industry, url, forward_to, voice_en, voice_es, slogan_en, slogan_es) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uc_id, data.get("name", ""), data.get("industry", ""), data.get("url", ""),
             data.get("forward_to", ""),
             v.get("en", ""), v.get("es", ""), sl.get("en", ""), sl.get("es", "")),
        )
        # Replace all topics for this use case
        con.execute("DELETE FROM topics WHERE use_case_id = ?", (uc_id,))
        for key, t in data.get("topics", {}).items():
            en = t.get("en", {})
            es = t.get("es", {})
            con.execute(
                "INSERT INTO topics (use_case_id, key, digit, meeting_type, "
                "label_en, label_es, menu_text_en, menu_text_es, "
                "greeting_en, greeting_es, system_extra_en, system_extra_es, "
                "questions_en, questions_es) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uc_id, key, t.get("digit", ""), 1 if t.get("meeting_type") else 0,
                    en.get("label", ""), es.get("label", ""),
                    en.get("menu_text", ""), es.get("menu_text", ""),
                    en.get("greeting", ""), es.get("greeting", ""),
                    en.get("system_extra", ""), es.get("system_extra", ""),
                    json.dumps(en.get("questions", []), ensure_ascii=False),
                    json.dumps(es.get("questions", []), ensure_ascii=False),
                ),
            )
        con.commit()


def uc_delete(uc_id: str):
    with _lock, _conn() as con:
        con.execute("DELETE FROM topics WHERE use_case_id = ?", (uc_id,))
        con.execute("DELETE FROM use_cases WHERE id = ?", (uc_id,))
        con.commit()


def migrate_use_cases_from_json():
    """Seed use_cases/topics tables from use_cases.json if the table is empty."""
    with _conn() as con:
        count = con.execute("SELECT COUNT(*) FROM use_cases").fetchone()[0]
    if count > 0:
        return
    json_path = Path(__file__).parent / "use_cases.json"
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for uc_id, uc in data.items():
            uc_upsert(uc_id, uc)
    except Exception as e:
        print(f"[DB] migrate_use_cases_from_json error: {e}")


# ── Users / Roles ─────────────────────────────────────────────────────────────

def _row_to_user(row) -> dict:
    return {
        "id":             row["id"],
        "first_name":     row["first_name"],
        "last_name":      row["last_name"],
        "email":          row["email"],
        "phone":          row["phone"] or "",
        "role_id":        row["role_id"],
        "role":           row["role_name"] if "role_name" in row.keys() else "",
        "email_verified": bool(row["email_verified"]),
        "phone_verified": bool(row["phone_verified"]),
        "is_active":      bool(row["is_active"]),
        "created_at":     row["created_at"] or "",
    }


def roles_list() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM roles ORDER BY id").fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def user_get(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT u.*, r.name AS role_name FROM users u "
            "JOIN roles r ON r.id = u.role_id WHERE u.id = ?",
            (user_id,)
        ).fetchone()
    return _row_to_user(row) if row else None


def user_get_by_email(email: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT u.*, r.name AS role_name FROM users u "
            "JOIN roles r ON r.id = u.role_id WHERE u.email = ?",
            (email.lower().strip(),)
        ).fetchone()
    return _row_to_user(row) if row else None


def user_get_password_hash(user_id: int) -> str:
    with _conn() as con:
        row = con.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["password_hash"] if row else ""


def user_check_password(email: str, password: str) -> dict | None:
    """Return user dict if credentials are valid, else None."""
    with _conn() as con:
        row = con.execute(
            "SELECT u.*, r.name AS role_name FROM users u "
            "JOIN roles r ON r.id = u.role_id WHERE u.email = ?",
            (email.lower().strip(),)
        ).fetchone()
    if not row:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return _row_to_user(row)


def user_list() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT u.*, r.name AS role_name FROM users u "
            "JOIN roles r ON r.id = u.role_id ORDER BY u.created_at DESC"
        ).fetchall()
    return [_row_to_user(r) for r in rows]


def user_create(first_name: str, last_name: str, email: str, phone: str,
                password: str, role_id: int) -> int:
    """Create a new user and return their id. Raises ValueError on duplicate email."""
    token = secrets.token_urlsafe(32)
    pw_hash = generate_password_hash(password)
    with _lock, _conn() as con:
        try:
            cur = con.execute(
                "INSERT INTO users (first_name, last_name, email, phone, password_hash, role_id, email_token) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (first_name, last_name, email.lower().strip(), phone, pw_hash, role_id, token),
            )
            con.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("Email already exists")


def user_update(user_id: int, data: dict):
    """Update editable user fields. Omit keys that should not be changed."""
    fields, values = [], []
    for col in ("first_name", "last_name", "phone", "role_id"):
        if col in data:
            fields.append(f"{col} = ?")
            values.append(data[col])
    if "password" in data and data["password"]:
        fields.append("password_hash = ?")
        values.append(generate_password_hash(data["password"]))
    if not fields:
        return
    values.append(user_id)
    with _lock, _conn() as con:
        con.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        con.commit()


def user_delete(user_id: int):
    with _lock, _conn() as con:
        con.execute("DELETE FROM users WHERE id = ?", (user_id,))
        con.commit()


def user_set_email_verified(user_id: int):
    with _lock, _conn() as con:
        con.execute(
            "UPDATE users SET email_verified = 1, email_token = NULL WHERE id = ?",
            (user_id,)
        )
        con.commit()
    _user_activate_if_ready(user_id)


def user_set_phone_verified(user_id: int):
    with _lock, _conn() as con:
        con.execute("UPDATE users SET phone_verified = 1 WHERE id = ?", (user_id,))
        con.commit()
    _user_activate_if_ready(user_id)


def _user_activate_if_ready(user_id: int):
    with _lock, _conn() as con:
        row = con.execute(
            "SELECT email_verified, phone_verified FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row and row["email_verified"] and row["phone_verified"]:
            con.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
            con.commit()


def user_get_by_email_token(token: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT u.*, r.name AS role_name FROM users u "
            "JOIN roles r ON r.id = u.role_id WHERE u.email_token = ?",
            (token,)
        ).fetchone()
    return _row_to_user(row) if row else None


def user_assign_use_cases(user_id: int, uc_ids: list):
    with _lock, _conn() as con:
        con.execute("DELETE FROM user_use_cases WHERE user_id = ?", (user_id,))
        for uc_id in uc_ids:
            con.execute(
                "INSERT OR IGNORE INTO user_use_cases (user_id, use_case_id) VALUES (?, ?)",
                (user_id, uc_id)
            )
        con.commit()


def user_get_use_cases(user_id: int) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT use_case_id FROM user_use_cases WHERE user_id = ?", (user_id,)
        ).fetchall()
    return [r["use_case_id"] for r in rows]


def seed_roles_and_admin():
    """Seed the roles table (admin, manager, standard). Admin user is created via /admin/setup."""
    with _lock, _conn() as con:
        for name in ("admin", "manager", "standard"):
            con.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (name,))
        con.commit()


def has_users() -> bool:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0


# ── Pending first-admin setup (not yet in users table) ────────────────────────

def pending_setup_save(data: dict):
    """Store first-admin form data temporarily until email is verified."""
    config_set("_pending_setup", json.dumps(data))


def pending_setup_get() -> dict | None:
    raw = config_get("_pending_setup")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def pending_setup_get_by_token(token: str) -> dict | None:
    data = pending_setup_get()
    if data and data.get("token") == token:
        return data
    return None


def pending_setup_clear():
    with _lock, _conn() as con:
        con.execute("DELETE FROM config WHERE key = '_pending_setup'")
        con.commit()


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def init():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id            TEXT PRIMARY KEY,
                datetime      TEXT,
                caller_number TEXT,
                caller_name   TEXT,
                topic         TEXT,
                language      TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS use_cases (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                industry    TEXT,
                url         TEXT,
                forward_to  TEXT,
                voice_en    TEXT,
                voice_es    TEXT,
                slogan_en   TEXT,
                slogan_es   TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                use_case_id     TEXT NOT NULL REFERENCES use_cases(id) ON DELETE CASCADE,
                key             TEXT NOT NULL,
                digit           TEXT,
                meeting_type    INTEGER DEFAULT 0,
                label_en        TEXT,
                label_es        TEXT,
                menu_text_en    TEXT,
                menu_text_es    TEXT,
                greeting_en     TEXT,
                greeting_es     TEXT,
                system_extra_en TEXT,
                system_extra_es TEXT,
                questions_en    TEXT DEFAULT '[]',
                questions_es    TEXT DEFAULT '[]',
                UNIQUE(use_case_id, key)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name     TEXT NOT NULL,
                last_name      TEXT NOT NULL,
                email          TEXT UNIQUE NOT NULL,
                phone          TEXT,
                password_hash  TEXT NOT NULL,
                role_id        INTEGER NOT NULL REFERENCES roles(id),
                email_verified INTEGER DEFAULT 0,
                phone_verified INTEGER DEFAULT 0,
                is_active      INTEGER DEFAULT 0,
                email_token    TEXT,
                created_at     TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS user_use_cases (
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                use_case_id TEXT    NOT NULL REFERENCES use_cases(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, use_case_id)
            )
        """)
        # Add forward_to to existing use_cases tables that predate this column
        try:
            con.execute("ALTER TABLE use_cases ADD COLUMN forward_to TEXT")
        except Exception:
            pass  # column already exists
        con.commit()


init()
migrate_config_from_json()
migrate_reports_from_json()
migrate_use_cases_from_json()
seed_roles_and_admin()
