# Feature: aws-migration, Property 3: Pre-signed URL correctness
"""
Property-based test for pre-signed URL correctness.

For any valid S3 asset key (audio file path), generating a pre-signed URL
should produce a URL that references the correct bucket and key, and has an
expiration time within the configured 1-hour window.

**Validates: Requirements 7.4**
"""
import os
import sys
from unittest.mock import MagicMock, patch
from urllib.parse import quote

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Strategies ────────────────────────────────────────────────────────────────

# Characters valid in S3 key path segments (alphanumeric + common safe chars)
_key_segment_chars = st.characters(
    whitelist_categories=("L", "N"),
    whitelist_characters="-_.",
)

# A single path segment (e.g., "intro", "wait-music-abc123", "report01")
_path_segment = st.text(
    alphabet=_key_segment_chars,
    min_size=1,
    max_size=40,
)

# Audio file extensions
_audio_extension = st.sampled_from([".wav", ".mp3"])

# Use-case ID for parameterized asset names
_use_case_id = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=20,
)

# Strategy for valid S3 asset keys matching the project's patterns:
#   - assets/intro.wav
#   - assets/wait-music-{id}.wav
#   - reports/{id}.mp3
_asset_key_strategy = st.one_of(
    # Pattern: assets/{filename}.{ext}
    st.builds(
        lambda segment, ext: f"assets/{segment}{ext}",
        segment=_path_segment,
        ext=_audio_extension,
    ),
    # Pattern: assets/wait-music-{use_case_id}.wav
    st.builds(
        lambda uc_id: f"assets/wait-music-{uc_id}.wav",
        uc_id=_use_case_id,
    ),
    # Pattern: reports/{id}.mp3
    st.builds(
        lambda segment: f"reports/{segment}.mp3",
        segment=_path_segment,
    ),
)


# ── Helpers ───────────────────────────────────────────────────────────────────

TEST_BUCKET = "test-audio-bucket"


def _make_storage():
    """Create an S3Storage instance with a mocked boto3 client.

    The mock's generate_presigned_url returns a URL that encodes the
    bucket and key parameters so we can verify them in assertions.
    """
    with patch.dict(os.environ, {
        "AWS_REGION": "us-west-2",
        "S3_REPORTS_BUCKET": "test-reports-bucket",
        "S3_AUDIO_BUCKET": TEST_BUCKET,
    }):
        with patch("src.storage.AWS_REGION", "us-west-2"), \
             patch("src.storage.S3_REPORTS_BUCKET", "test-reports-bucket"), \
             patch("src.storage.S3_AUDIO_BUCKET", TEST_BUCKET):
            with patch("boto3.client") as mock_boto:
                mock_client = MagicMock()
                mock_boto.return_value = mock_client

                # Mock generate_presigned_url to return a URL containing
                # the bucket and key so we can verify correctness
                def fake_presigned_url(method, Params, ExpiresIn):
                    bucket = Params["Bucket"]
                    key = Params["Key"]
                    return (
                        f"https://{bucket}.s3.amazonaws.com/"
                        f"{quote(key, safe='/')}?X-Amz-Expires={ExpiresIn}"
                    )

                mock_client.generate_presigned_url.side_effect = fake_presigned_url

                from src.storage import S3Storage
                instance = S3Storage()
                instance._client = mock_client
                return instance, mock_client


# ── Property Test ─────────────────────────────────────────────────────────────


class TestPreSignedUrlCorrectness:
    """Property 3: Pre-signed URL correctness.

    For any valid S3 asset key, generating a pre-signed URL should produce
    a URL that references the correct bucket and key, and has an expiration
    time within the configured 1-hour window.

    **Validates: Requirements 7.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(asset_key=_asset_key_strategy)
    def test_presigned_url_contains_correct_bucket(self, asset_key):
        """The generated pre-signed URL references the correct S3 bucket."""
        storage, mock_client = _make_storage()

        url = storage.get_audio_url(asset_key)

        assert TEST_BUCKET in url

    @settings(max_examples=100, deadline=None)
    @given(asset_key=_asset_key_strategy)
    def test_presigned_url_contains_correct_key(self, asset_key):
        """The generated pre-signed URL references the correct S3 key."""
        storage, mock_client = _make_storage()

        url = storage.get_audio_url(asset_key)

        # The key should appear in the URL (URL-encoded for safety)
        assert quote(asset_key, safe="/") in url

    @settings(max_examples=100, deadline=None)
    @given(asset_key=_asset_key_strategy)
    def test_presigned_url_expiry_is_one_hour(self, asset_key):
        """The expiry parameter passed to generate_presigned_url is 3600 (1 hour)."""
        storage, mock_client = _make_storage()

        storage.get_audio_url(asset_key)

        # Verify the call was made with ExpiresIn=3600
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": TEST_BUCKET, "Key": asset_key},
            ExpiresIn=3600,
        )

    @settings(max_examples=100, deadline=None)
    @given(asset_key=_asset_key_strategy)
    def test_presigned_url_uses_get_object_method(self, asset_key):
        """The pre-signed URL is generated for the 'get_object' S3 method."""
        storage, mock_client = _make_storage()

        storage.get_audio_url(asset_key)

        call_args = mock_client.generate_presigned_url.call_args
        assert call_args[0][0] == "get_object"
