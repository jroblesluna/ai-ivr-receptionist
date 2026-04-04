"""
SQLite storage for call reports index and runtime configuration.
DB file: data/app.db (persisted via Railway Volume at /app/data)
"""
import json
import sqlite3
import threading
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
_lock = threading.Lock()


def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


# ── Schema ────────────────────────────────────────────────────────────────────

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
        con.commit()


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
    """Seed config table from runtime_config.json if it exists and config is empty."""
    json_path = Path(__file__).parent.parent / "data" / "runtime_config.json"
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        config_seed(data)
    except Exception:
        pass


# ── Bootstrap ─────────────────────────────────────────────────────────────────

init()
migrate_config_from_json()
migrate_reports_from_json()
