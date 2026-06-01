# Feature: aws-migration, Property 5: Fernet decryption round-trip during migration
"""
Property-based test for Fernet decryption round-trip during migration.

For any string value that was encrypted with Fernet using a known SECRET_KEY,
the migration script's decryption step should recover the original plaintext
value exactly.

**Validates: Requirements 9.3**
"""
import sys
import os

import pytest
from cryptography.fernet import Fernet
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.migrate_railway_to_aws import decrypt_fernet_value


# ── Strategies ────────────────────────────────────────────────────────────────

# Random plaintext strings including unicode, empty, and long values
plaintext_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
    max_size=5000,
)


# ── Property Test ─────────────────────────────────────────────────────────────

class TestFernetDecryptionRoundTrip:
    """Property 5: Fernet decryption round-trip during migration.

    For any string value that was encrypted with Fernet using a known SECRET_KEY,
    the migration script's decryption step should recover the original plaintext
    value exactly.

    **Validates: Requirements 9.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(plaintext=plaintext_strategy)
    def test_decrypt_recovers_original_plaintext(self, plaintext):
        """Encrypting a plaintext with Fernet and decrypting via decrypt_fernet_value
        should recover the original plaintext exactly."""
        # Generate a random Fernet key for each test case
        key = Fernet.generate_key()
        fernet = Fernet(key)

        # Encrypt the plaintext
        encrypted = fernet.encrypt(plaintext.encode()).decode()

        # Decrypt via the migration script's function
        decrypted = decrypt_fernet_value(encrypted, fernet)

        # Verify round-trip preserves the original value
        assert decrypted == plaintext

    @settings(max_examples=100, deadline=None)
    @given(
        plaintext=plaintext_strategy,
        key=st.binary(min_size=32, max_size=32).map(
            lambda b: Fernet.generate_key()
        ),
    )
    def test_decrypt_with_generated_keys(self, plaintext, key):
        """Decryption works correctly across different randomly generated keys."""
        fernet = Fernet(key)

        # Encrypt the plaintext
        encrypted = fernet.encrypt(plaintext.encode()).decode()

        # Decrypt via the migration script's function
        decrypted = decrypt_fernet_value(encrypted, fernet)

        # Verify round-trip preserves the original value
        assert decrypted == plaintext

    @settings(max_examples=100, deadline=None)
    @given(plaintext=st.text(min_size=0, max_size=0))
    def test_decrypt_empty_string(self, plaintext):
        """Empty strings are correctly handled in the round-trip."""
        key = Fernet.generate_key()
        fernet = Fernet(key)

        encrypted = fernet.encrypt(plaintext.encode()).decode()
        decrypted = decrypt_fernet_value(encrypted, fernet)

        assert decrypted == plaintext

    @settings(max_examples=100, deadline=None)
    @given(
        plaintext=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "M", "N", "P", "S", "Z"),
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=2000,
        )
    )
    def test_decrypt_unicode_content(self, plaintext):
        """Unicode content (including emojis, CJK, Arabic, etc.) survives the round-trip."""
        key = Fernet.generate_key()
        fernet = Fernet(key)

        encrypted = fernet.encrypt(plaintext.encode()).decode()
        decrypted = decrypt_fernet_value(encrypted, fernet)

        assert decrypted == plaintext
