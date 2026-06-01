"""
S3-backed file storage for reports and audio assets.

When AWS_REGION is set, uses S3 for all file operations.
When AWS_REGION is not set (local dev), falls back to local filesystem.
"""
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Environment configuration ─────────────────────────────────────────────────

AWS_REGION = os.environ.get("AWS_REGION", "")
S3_REPORTS_BUCKET = os.environ.get("S3_REPORTS_BUCKET", "")
S3_AUDIO_BUCKET = os.environ.get("S3_AUDIO_BUCKET", "")

# Local filesystem paths (used when AWS_REGION is not set)
_REPORTS_DIR = Path(__file__).parent.parent / "data" / "reports"
_ASSETS_DIR = Path(__file__).parent.parent / "assets"


class S3Storage:
    """S3-backed file storage for reports and audio.

    Falls back to local filesystem when AWS_REGION is not set.
    """

    def __init__(self) -> None:
        self._client = None
        if AWS_REGION:
            import boto3

            self._client = boto3.client("s3", region_name=AWS_REGION)

    def upload_report(self, report_id: str, data: dict) -> None:
        """Upload report JSON to S3.

        S3 key: reports/{report_id}.json
        """
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        key = f"reports/{report_id}.json"

        if self._client:
            self.upload_with_retry(S3_REPORTS_BUCKET, key, body)
        else:
            _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            (_REPORTS_DIR / f"{report_id}.json").write_bytes(body)

    def upload_audio(
        self, report_id: str, audio_bytes: bytes, suffix: str = ".mp3"
    ) -> None:
        """Upload call recording to S3.

        S3 key: reports/{report_id}{suffix}
        Supported suffixes: .mp3, .recording.mp3
        """
        key = f"reports/{report_id}{suffix}"

        if self._client:
            self.upload_with_retry(S3_REPORTS_BUCKET, key, audio_bytes)
        else:
            _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            (_REPORTS_DIR / f"{report_id}{suffix}").write_bytes(audio_bytes)

    def get_report(self, report_id: str) -> dict | None:
        """Download and parse report JSON from S3.

        Returns None if the report does not exist.
        Raises an exception (caught by caller) on transient failures
        so the route can return HTTP 503.
        """
        key = f"reports/{report_id}.json"

        if self._client:
            try:
                response = self._client.get_object(
                    Bucket=S3_REPORTS_BUCKET, Key=key
                )
                body = response["Body"].read()
                return json.loads(body)
            except self._client.exceptions.NoSuchKey:
                return None
            except Exception as exc:
                logger.error(
                    "Failed to download report %s from S3: %s", report_id, exc
                )
                raise StorageDownloadError(
                    f"Failed to retrieve report {report_id}"
                ) from exc
        else:
            path = _REPORTS_DIR / f"{report_id}.json"
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

    def get_audio_url(self, asset_key: str, expiry: int = 3600) -> str:
        """Generate pre-signed URL for audio asset (1-hour expiry).

        asset_key should be the full S3 key, e.g. 'assets/intro.wav'
        or 'reports/{id}.mp3'.
        """
        if self._client:
            try:
                url = self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_AUDIO_BUCKET, "Key": asset_key},
                    ExpiresIn=expiry,
                )
                return url
            except Exception as exc:
                logger.error(
                    "Failed to generate pre-signed URL for %s: %s",
                    asset_key,
                    exc,
                )
                raise
        else:
            # Local dev: return a relative path for local serving
            return f"/{asset_key.replace('assets/', '')}"

    def upload_with_retry(
        self, bucket: str, key: str, body: bytes, retries: int = 2
    ) -> None:
        """Upload to S3 with retry logic (2 retries, 1s delay between attempts).

        Total attempts = 1 initial + retries.
        On final failure, logs the error and continues without blocking.
        """
        last_exc: Exception | None = None
        attempts = 1 + retries  # initial attempt + retries

        for attempt in range(attempts):
            try:
                self._client.put_object(Bucket=bucket, Key=key, Body=body)
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "S3 upload attempt %d/%d failed for %s/%s: %s",
                    attempt + 1,
                    attempts,
                    bucket,
                    key,
                    exc,
                )
                if attempt < attempts - 1:
                    time.sleep(1)

        # All retries exhausted — log and continue without blocking
        logger.error(
            "S3 upload failed after %d attempts for %s/%s: %s",
            attempts,
            bucket,
            key,
            last_exc,
        )


class StorageDownloadError(Exception):
    """Raised when a download from S3 fails (triggers HTTP 503)."""

    pass


# ── Module-level singleton ────────────────────────────────────────────────────

storage = S3Storage()
