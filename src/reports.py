"""
Persistent call report storage.
Reports are uploaded to S3 (or local filesystem when AWS_REGION is not set).
Served via /report/<id>.
"""
import uuid
import db
from storage import storage


def save(data: dict) -> str:
    """Save report JSON to S3 and insert into database."""
    report_id = uuid.uuid4().hex[:16]
    data["id"] = report_id
    storage.upload_report(report_id, data)
    db.report_insert(report_id, data)
    return report_id


def load(report_id: str) -> dict | None:
    """Load report JSON from S3."""
    return storage.get_report(report_id)


def save_audio(report_id: str, audio_bytes: bytes, suffix: str = ".mp3") -> None:
    """Upload audio bytes to S3."""
    storage.upload_audio(report_id, audio_bytes, suffix=suffix)


def get_audio_url(report_id: str, suffix: str = ".mp3") -> str:
    """Get a pre-signed URL for report audio."""
    return storage.get_audio_url(f"reports/{report_id}{suffix}")
