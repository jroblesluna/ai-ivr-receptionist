"""
Unit tests for src/storage.py — S3Storage class.

Tests cover:
- upload_report (S3 and local fallback)
- upload_audio (S3 and local fallback)
- get_report (success, not found, download failure)
- get_audio_url (pre-signed URL generation)
- upload_with_retry (retry logic: 2 retries, 1s delay)
- StorageDownloadError triggers HTTP 503 behavior

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def s3_storage_aws():
    """Create an S3Storage instance with a mocked boto3 client (AWS mode)."""
    with patch.dict(os.environ, {
        "AWS_REGION": "us-west-2",
        "S3_REPORTS_BUCKET": "test-reports-bucket",
        "S3_AUDIO_BUCKET": "test-audio-bucket",
    }):
        with patch("src.storage.AWS_REGION", "us-west-2"), \
             patch("src.storage.S3_REPORTS_BUCKET", "test-reports-bucket"), \
             patch("src.storage.S3_AUDIO_BUCKET", "test-audio-bucket"):
            with patch("boto3.client") as mock_boto:
                mock_client = MagicMock()
                mock_boto.return_value = mock_client
                from src.storage import S3Storage
                instance = S3Storage()
                instance._client = mock_client
                yield instance, mock_client


@pytest.fixture
def s3_storage_local(tmp_path):
    """Create an S3Storage instance in local fallback mode."""
    with patch("src.storage.AWS_REGION", ""), \
         patch("src.storage._REPORTS_DIR", tmp_path / "reports"), \
         patch("src.storage._ASSETS_DIR", tmp_path / "assets"):
        from src.storage import S3Storage
        instance = S3Storage()
        instance._client = None
        yield instance, tmp_path


# ── Tests: upload_report ──────────────────────────────────────────────────────


class TestUploadReport:
    """Validates: Requirement 7.1 — upload JSON report to S3."""

    def test_upload_report_s3(self, s3_storage_aws):
        """Uploads report JSON to S3 with correct key structure."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.return_value = {}

        data = {"id": "abc123", "topic": "billing", "summary": "Test report"}
        storage.upload_report("abc123", data)

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-reports-bucket"
        assert call_kwargs["Key"] == "reports/abc123.json"
        body = json.loads(call_kwargs["Body"])
        assert body == data

    def test_upload_report_local(self, s3_storage_local):
        """Falls back to local filesystem when AWS_REGION is not set."""
        storage, tmp_path = s3_storage_local
        data = {"id": "local1", "topic": "test"}

        with patch("src.storage._REPORTS_DIR", tmp_path / "reports"):
            storage.upload_report("local1", data)

        report_file = tmp_path / "reports" / "local1.json"
        assert report_file.exists()
        assert json.loads(report_file.read_text()) == data


# ── Tests: upload_audio ───────────────────────────────────────────────────────


class TestUploadAudio:
    """Validates: Requirement 7.1 — upload audio files to S3."""

    def test_upload_audio_mp3(self, s3_storage_aws):
        """Uploads MP3 audio with correct key: reports/{id}.mp3."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.return_value = {}

        audio_bytes = b"\xff\xfb\x90\x00" * 100
        storage.upload_audio("abc123", audio_bytes)

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "reports/abc123.mp3"
        assert call_kwargs["Body"] == audio_bytes

    def test_upload_audio_recording_suffix(self, s3_storage_aws):
        """Uploads recording with .recording.mp3 suffix."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.return_value = {}

        audio_bytes = b"\xff\xfb\x90\x00" * 50
        storage.upload_audio("abc123", audio_bytes, suffix=".recording.mp3")

        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "reports/abc123.recording.mp3"

    def test_upload_audio_local(self, s3_storage_local):
        """Falls back to local filesystem for audio uploads."""
        storage, tmp_path = s3_storage_local
        audio_bytes = b"\xff\xfb\x90\x00" * 10

        with patch("src.storage._REPORTS_DIR", tmp_path / "reports"):
            storage.upload_audio("local1", audio_bytes)

        audio_file = tmp_path / "reports" / "local1.mp3"
        assert audio_file.exists()
        assert audio_file.read_bytes() == audio_bytes


# ── Tests: get_report ─────────────────────────────────────────────────────────


class TestGetReport:
    """Validates: Requirement 7.2 — retrieve report JSON from S3."""

    def test_get_report_success(self, s3_storage_aws):
        """Successfully downloads and parses report JSON."""
        storage, mock_client = s3_storage_aws
        report_data = {"id": "rpt1", "topic": "sales", "summary": "Good call"}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(report_data).encode("utf-8")
        mock_client.get_object.return_value = {"Body": mock_body}

        result = storage.get_report("rpt1")

        assert result == report_data
        mock_client.get_object.assert_called_once_with(
            Bucket="test-reports-bucket", Key="reports/rpt1.json"
        )

    def test_get_report_not_found(self, s3_storage_aws):
        """Returns None when report does not exist in S3."""
        storage, mock_client = s3_storage_aws
        # Simulate NoSuchKey exception
        mock_client.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_client.get_object.side_effect = mock_client.exceptions.NoSuchKey(
            "Not found"
        )

        result = storage.get_report("nonexistent")
        assert result is None

    def test_get_report_download_failure_raises(self, s3_storage_aws):
        """Raises StorageDownloadError on transient S3 failure (HTTP 503)."""
        from src.storage import StorageDownloadError

        storage, mock_client = s3_storage_aws
        mock_client.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_client.get_object.side_effect = RuntimeError("Connection timeout")

        with pytest.raises(StorageDownloadError):
            storage.get_report("fail_report")

    def test_get_report_local_exists(self, s3_storage_local):
        """Returns report data from local filesystem."""
        storage, tmp_path = s3_storage_local
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        data = {"id": "loc1", "topic": "test"}
        (reports_dir / "loc1.json").write_text(json.dumps(data))

        with patch("src.storage._REPORTS_DIR", reports_dir):
            result = storage.get_report("loc1")

        assert result == data

    def test_get_report_local_not_found(self, s3_storage_local):
        """Returns None when local report file does not exist."""
        storage, tmp_path = s3_storage_local

        with patch("src.storage._REPORTS_DIR", tmp_path / "reports"):
            result = storage.get_report("missing")

        assert result is None


# ── Tests: get_audio_url ──────────────────────────────────────────────────────


class TestGetAudioUrl:
    """Validates: Requirement 7.4 — pre-signed URL with 1-hour expiry."""

    def test_get_audio_url_generates_presigned(self, s3_storage_aws):
        """Generates a pre-signed URL with correct bucket, key, and expiry."""
        storage, mock_client = s3_storage_aws
        mock_client.generate_presigned_url.return_value = (
            "https://test-audio-bucket.s3.amazonaws.com/assets/intro.wav?sig=abc"
        )

        url = storage.get_audio_url("assets/intro.wav")

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-audio-bucket", "Key": "assets/intro.wav"},
            ExpiresIn=3600,
        )
        assert "intro.wav" in url

    def test_get_audio_url_custom_expiry(self, s3_storage_aws):
        """Respects custom expiry parameter."""
        storage, mock_client = s3_storage_aws
        mock_client.generate_presigned_url.return_value = "https://example.com"

        storage.get_audio_url("assets/wait-music.wav", expiry=1800)

        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == 1800

    def test_get_audio_url_local_fallback(self, s3_storage_local):
        """Returns relative path in local dev mode."""
        storage, _ = s3_storage_local

        url = storage.get_audio_url("assets/intro.wav")
        assert url == "/intro.wav"

    def test_get_audio_url_local_wait_music(self, s3_storage_local):
        """Returns correct relative path for wait-music assets."""
        storage, _ = s3_storage_local

        url = storage.get_audio_url("assets/wait-music-chem_supply.wav")
        assert url == "/wait-music-chem_supply.wav"


# ── Tests: upload_with_retry ──────────────────────────────────────────────────


class TestUploadWithRetry:
    """Validates: Requirement 7.5 — retry logic (2 retries, 1s delay)."""

    def test_succeeds_on_first_attempt(self, s3_storage_aws):
        """No retries needed when upload succeeds immediately."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.return_value = {}

        storage.upload_with_retry(
            "test-bucket", "test/key.json", b"data"
        )

        assert mock_client.put_object.call_count == 1

    def test_retries_on_failure_then_succeeds(self, s3_storage_aws):
        """Retries once and succeeds on second attempt."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.side_effect = [
            RuntimeError("Network error"),
            {},  # success on second attempt
        ]

        with patch("src.storage.time.sleep") as mock_sleep:
            storage.upload_with_retry(
                "test-bucket", "test/key.json", b"data"
            )

        assert mock_client.put_object.call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_retries_twice_then_succeeds(self, s3_storage_aws):
        """Retries twice and succeeds on third attempt."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.side_effect = [
            RuntimeError("Error 1"),
            RuntimeError("Error 2"),
            {},  # success on third attempt
        ]

        with patch("src.storage.time.sleep") as mock_sleep:
            storage.upload_with_retry(
                "test-bucket", "test/key.json", b"data"
            )

        assert mock_client.put_object.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(1), call(1)])

    def test_all_retries_exhausted_logs_error(self, s3_storage_aws):
        """After 3 failed attempts, logs error and continues (no exception)."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.side_effect = RuntimeError("Persistent failure")

        with patch("src.storage.time.sleep") as mock_sleep:
            # Should NOT raise — continues without blocking
            storage.upload_with_retry(
                "test-bucket", "test/key.json", b"data"
            )

        assert mock_client.put_object.call_count == 3
        assert mock_sleep.call_count == 2

    def test_delay_is_one_second_between_retries(self, s3_storage_aws):
        """Verifies 1-second delay between each retry attempt."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.side_effect = RuntimeError("fail")

        with patch("src.storage.time.sleep") as mock_sleep:
            storage.upload_with_retry(
                "test-bucket", "test/key.json", b"data"
            )

        # All sleep calls should be 1 second
        for c in mock_sleep.call_args_list:
            assert c == call(1)

    def test_custom_retries_parameter(self, s3_storage_aws):
        """Respects custom retries parameter."""
        storage, mock_client = s3_storage_aws
        mock_client.put_object.side_effect = RuntimeError("fail")

        with patch("src.storage.time.sleep"):
            storage.upload_with_retry(
                "test-bucket", "test/key.json", b"data", retries=1
            )

        # 1 initial + 1 retry = 2 total attempts
        assert mock_client.put_object.call_count == 2
