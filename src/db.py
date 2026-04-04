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


# ── Use Cases ─────────────────────────────────────────────────────────────────

def _row_to_uc(row) -> dict:
    return {
        "id":       row["id"],
        "name":     row["name"],
        "industry": row["industry"] or "",
        "url":      row["url"] or "",
        "voice":    {"en": row["voice_en"] or "", "es": row["voice_es"] or ""},
        "slogan":   {"en": row["slogan_en"] or "", "es": row["slogan_es"] or ""},
        "topics":   {},
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
            "INSERT OR REPLACE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uc_id, data.get("name", ""), data.get("industry", ""), data.get("url", ""),
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
        con.commit()


init()
migrate_config_from_json()
migrate_reports_from_json()
migrate_use_cases_from_json()
