"""
Persistent call report storage.
Reports are saved as JSON files under data/reports/ and served via /report/<id>.
"""
import json
import uuid
from pathlib import Path
import db

_DIR = Path(__file__).parent.parent / "data" / "reports"


def save(data: dict) -> str:
    _DIR.mkdir(parents=True, exist_ok=True)
    report_id = uuid.uuid4().hex[:16]
    data["id"] = report_id
    (_DIR / f"{report_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    db.report_insert(report_id, data)
    return report_id


def load(report_id: str) -> dict | None:
    path = _DIR / f"{report_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def audio_path(report_id: str) -> Path:
    return _DIR / f"{report_id}.mp3"


def recording_path(report_id: str) -> Path:
    return _DIR / f"{report_id}.recording.mp3"
