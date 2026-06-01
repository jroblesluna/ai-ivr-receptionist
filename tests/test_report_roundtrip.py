# Feature: aws-migration, Property 2: Report storage round-trip preservation
"""
Property-based test for report storage round-trip preservation.

For any valid report JSON object (containing timestamp, caller info,
conversation history, and summary fields), uploading it to S3 and then
downloading it should produce a JSON object identical to the original.

**Validates: Requirements 7.2**
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Strategies ────────────────────────────────────────────────────────────────

# Safe text that avoids null bytes (invalid in JSON strings) and surrogates
safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=200,
)

safe_text_short = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=50,
)

# Timestamp strings (ISO-like format)
timestamp_strategy = st.from_regex(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}",
    fullmatch=True,
)

# Caller info with phone number and name
caller_info_strategy = st.fixed_dictionaries({
    "caller_number": safe_text_short,
    "caller_name": st.one_of(st.none(), safe_text_short),
    "topic": safe_text_short,
    "language": st.sampled_from(["en", "es", ""]),
})

# A single conversation message
message_strategy = st.fixed_dictionaries({
    "role": st.sampled_from(["system", "user", "assistant"]),
    "content": safe_text,
})

# Conversation history: 0–50 messages
conversation_strategy = st.lists(message_strategy, min_size=0, max_size=50)

# Report ID: alphanumeric string suitable for filenames
report_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=5,
    max_size=16,
)

# Full report object combining all fields
report_strategy = st.fixed_dictionaries({
    "id": report_id_strategy,
    "datetime": timestamp_strategy,
    "caller_number": safe_text_short,
    "caller_name": st.one_of(st.none(), safe_text_short),
    "topic": safe_text_short,
    "language": st.sampled_from(["en", "es", ""]),
    "conversation": conversation_strategy,
    "summary": safe_text,
})


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_storage(tmp_dir: Path):
    """Create a fresh S3Storage instance using local filesystem fallback."""
    with patch("src.storage.AWS_REGION", ""), \
         patch("src.storage._REPORTS_DIR", tmp_dir):
        from src.storage import S3Storage
        instance = S3Storage()
        instance._client = None
    return instance, tmp_dir


# ── Property Test ─────────────────────────────────────────────────────────────


class TestReportRoundTrip:
    """Property 2: Report storage round-trip preservation.

    For any valid report JSON object (containing timestamp, caller info,
    conversation history, and summary fields), uploading it to S3 and then
    downloading it should produce a JSON object identical to the original.

    **Validates: Requirements 7.2**
    """

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(report=report_strategy)
    def test_report_upload_download_round_trip(self, report, tmp_path):
        """Any valid report JSON survives an upload/download round-trip."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        with patch("src.storage._REPORTS_DIR", reports_dir):
            from src.storage import S3Storage
            storage = S3Storage()
            storage._client = None  # Force local fallback

            report_id = report["id"]

            # Upload
            storage.upload_report(report_id, report)

            # Download
            retrieved = storage.get_report(report_id)

        assert retrieved == report

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        report=report_strategy,
        extra_fields=st.dictionaries(
            keys=safe_text_short,
            values=st.one_of(
                safe_text,
                st.integers(min_value=-1000, max_value=1000),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans(),
                st.none(),
            ),
            min_size=0,
            max_size=5,
        ),
    )
    def test_report_with_extra_fields_round_trip(self, report, extra_fields, tmp_path):
        """Reports with additional arbitrary fields also survive round-trip."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Merge extra fields into the report
        full_report = {**report, **extra_fields}

        with patch("src.storage._REPORTS_DIR", reports_dir):
            from src.storage import S3Storage
            storage = S3Storage()
            storage._client = None

            report_id = report["id"]

            # Upload
            storage.upload_report(report_id, full_report)

            # Download
            retrieved = storage.get_report(report_id)

        assert retrieved == full_report
