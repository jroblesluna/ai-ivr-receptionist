# Feature: aws-migration, Property 4: Data migration preserves all records
"""
Property-based tests for:
1. SQLAlchemy model round-trip (data preservation) — validates Requirement 2.6, 2.7
2. Connection retry logic with exponential backoff — validates Requirement 2.6, 2.7

**Validates: Requirements 2.6, 2.7**
"""
import time
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import sys
import os

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import Base
from src.models.config import Config
from src.models.report import Report
from src.models.use_case import UseCase, Topic
from src.models.user import Role, User, UserUseCase
from src.models.caller_profile import CallerProfile


# ── Strategies ────────────────────────────────────────────────────────────────

# Constrained text strategies to avoid null bytes (invalid in PostgreSQL strings)
safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=100,
)

safe_text_short = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=50,
)

safe_text_id = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-",
    ),
    min_size=1,
    max_size=16,
)


config_strategy = st.builds(
    lambda key, value: {"key": key, "value": value},
    key=safe_text_short,
    value=st.one_of(safe_text, st.none()),
)

report_strategy = st.builds(
    lambda id_, dt, number, name, topic, lang: {
        "id": id_,
        "datetime": dt,
        "caller_number": number,
        "caller_name": name,
        "topic": topic,
        "language": lang,
    },
    id_=safe_text_id,
    dt=safe_text,
    number=safe_text,
    name=safe_text,
    topic=safe_text,
    lang=safe_text,
)

use_case_strategy = st.builds(
    lambda id_, name, industry, url, forward_to, voice_en, voice_es, slogan_en, slogan_es, is_demo, demo_code, ivr_type: {
        "id": id_,
        "name": name,
        "industry": industry,
        "url": url,
        "forward_to": forward_to,
        "voice_en": voice_en,
        "voice_es": voice_es,
        "slogan_en": slogan_en,
        "slogan_es": slogan_es,
        "is_demo": is_demo,
        "demo_code": demo_code,
        "ivr_type": ivr_type,
    },
    id_=safe_text_id,
    name=safe_text_short,
    industry=st.one_of(safe_text, st.none()),
    url=st.one_of(safe_text, st.none()),
    forward_to=st.one_of(safe_text, st.none()),
    voice_en=st.one_of(safe_text, st.none()),
    voice_es=st.one_of(safe_text, st.none()),
    slogan_en=st.one_of(safe_text, st.none()),
    slogan_es=st.one_of(safe_text, st.none()),
    is_demo=st.integers(min_value=0, max_value=1),
    demo_code=st.one_of(safe_text, st.none()),
    ivr_type=st.sampled_from(["topics", "direct", "menu"]),
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing model round-trips."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()
    engine.dispose()


# ── Property Tests: Model Round-Trip ──────────────────────────────────────────


class TestModelRoundTrip:
    """Property 4: Data migration preserves all records (model round-trip).

    For any valid record, inserting it into the database and reading it back
    should produce identical field values.

    **Validates: Requirements 2.6, 2.7**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=config_strategy)
    def test_config_round_trip(self, data, db_session):
        """Config records survive a write/read round-trip."""
        # Clean slate for each example
        db_session.query(Config).filter(Config.key == data["key"]).delete()
        db_session.commit()

        record = Config(key=data["key"], value=data["value"])
        db_session.add(record)
        db_session.commit()

        result = db_session.query(Config).filter(Config.key == data["key"]).first()
        assert result is not None
        assert result.key == data["key"]
        assert result.value == data["value"]

        # Cleanup
        db_session.delete(result)
        db_session.commit()

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=report_strategy)
    def test_report_round_trip(self, data, db_session):
        """Report records survive a write/read round-trip."""
        db_session.query(Report).filter(Report.id == data["id"]).delete()
        db_session.commit()

        record = Report(
            id=data["id"],
            datetime=data["datetime"],
            caller_number=data["caller_number"],
            caller_name=data["caller_name"],
            topic=data["topic"],
            language=data["language"],
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(Report).filter(Report.id == data["id"]).first()
        assert result is not None
        assert result.id == data["id"]
        assert result.datetime == data["datetime"]
        assert result.caller_number == data["caller_number"]
        assert result.caller_name == data["caller_name"]
        assert result.topic == data["topic"]
        assert result.language == data["language"]

        db_session.delete(result)
        db_session.commit()

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=use_case_strategy)
    def test_use_case_round_trip(self, data, db_session):
        """UseCase records survive a write/read round-trip."""
        db_session.query(UseCase).filter(UseCase.id == data["id"]).delete()
        db_session.commit()

        record = UseCase(
            id=data["id"],
            name=data["name"],
            industry=data["industry"],
            url=data["url"],
            forward_to=data["forward_to"],
            voice_en=data["voice_en"],
            voice_es=data["voice_es"],
            slogan_en=data["slogan_en"],
            slogan_es=data["slogan_es"],
            is_demo=data["is_demo"],
            demo_code=data["demo_code"],
            ivr_type=data["ivr_type"],
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.query(UseCase).filter(UseCase.id == data["id"]).first()
        assert result is not None
        assert result.id == data["id"]
        assert result.name == data["name"]
        assert result.industry == data["industry"]
        assert result.url == data["url"]
        assert result.forward_to == data["forward_to"]
        assert result.voice_en == data["voice_en"]
        assert result.voice_es == data["voice_es"]
        assert result.slogan_en == data["slogan_en"]
        assert result.slogan_es == data["slogan_es"]
        assert result.is_demo == data["is_demo"]
        assert result.demo_code == data["demo_code"]
        assert result.ivr_type == data["ivr_type"]

        db_session.delete(result)
        db_session.commit()


# ── Property Tests: Connection Retry Logic ────────────────────────────────────

# Import src.db module so patch targets resolve correctly
import src.db as _db_module  # noqa: E402


class TestConnectionRetryLogic:
    """Validates _with_retry decorator behavior.

    - Retries on OperationalError with exponential backoff (1s→2s→4s)
    - After 3 failed attempts, the error is raised

    **Validates: Requirements 2.6, 2.7**
    """

    def test_retry_succeeds_on_second_attempt(self):
        """_with_retry retries and succeeds when the second attempt works."""
        from src.db import _with_retry

        call_count = {"n": 0}
        sleep_calls = []

        @_with_retry
        def flaky_operation():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise OperationalError("connection failed", {}, None)
            return "success"

        with patch.object(_db_module.time, "sleep", side_effect=lambda s: sleep_calls.append(s)):
            result = flaky_operation()

        assert result == "success"
        assert call_count["n"] == 2
        assert sleep_calls == [1]

    def test_retry_succeeds_on_third_attempt(self):
        """_with_retry retries and succeeds when the third attempt works."""
        from src.db import _with_retry

        call_count = {"n": 0}
        sleep_calls = []

        @_with_retry
        def flaky_operation():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise OperationalError("connection failed", {}, None)
            return "success"

        with patch.object(_db_module.time, "sleep", side_effect=lambda s: sleep_calls.append(s)):
            result = flaky_operation()

        assert result == "success"
        assert call_count["n"] == 3
        # Should have slept with 1s then 2s (exponential backoff)
        assert sleep_calls == [1, 2]

    def test_retry_raises_after_max_attempts(self):
        """_with_retry raises OperationalError after 3 failed attempts."""
        from src.db import _with_retry

        call_count = {"n": 0}
        sleep_calls = []

        @_with_retry
        def always_fails():
            call_count["n"] += 1
            raise OperationalError("connection failed", {}, None)

        with patch.object(_db_module.time, "sleep", side_effect=lambda s: sleep_calls.append(s)):
            with pytest.raises(OperationalError):
                always_fails()

        assert call_count["n"] == 3
        assert sleep_calls == [1, 2]

    def test_retry_exponential_backoff_values(self):
        """Backoff follows 1s → 2s pattern (only 2 sleeps before 3rd attempt fails)."""
        from src.db import _with_retry

        sleep_calls = []

        @_with_retry
        def always_fails():
            raise OperationalError("connection failed", {}, None)

        with patch.object(_db_module.time, "sleep", side_effect=lambda s: sleep_calls.append(s)):
            with pytest.raises(OperationalError):
                always_fails()

        # With MAX_RETRIES=3, we get 2 sleep calls (before attempt 2 and 3)
        assert sleep_calls == [1, 2]

    def test_retry_does_not_catch_non_operational_errors(self):
        """_with_retry does not retry on non-OperationalError exceptions."""
        from src.db import _with_retry

        sleep_calls = []

        @_with_retry
        def raises_value_error():
            raise ValueError("not a DB error")

        with patch.object(_db_module.time, "sleep", side_effect=lambda s: sleep_calls.append(s)):
            with pytest.raises(ValueError):
                raises_value_error()

        # Should not have slept at all
        assert sleep_calls == []

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        failures_before_success=st.integers(min_value=0, max_value=2)
    )
    def test_retry_property_succeeds_within_max_attempts(
        self, failures_before_success
    ):
        """For any number of failures < MAX_RETRIES, the operation eventually succeeds."""
        from src.db import _with_retry

        call_count = {"n": 0}
        sleep_calls = []

        @_with_retry
        def operation():
            call_count["n"] += 1
            if call_count["n"] <= failures_before_success:
                raise OperationalError("connection failed", {}, None)
            return "ok"

        with patch.object(_db_module.time, "sleep", side_effect=lambda s: sleep_calls.append(s)):
            result = operation()

        assert result == "ok"
        assert call_count["n"] == failures_before_success + 1

        # Verify backoff values are correct: 1, 2, 4, ... (2^i for i in range)
        expected_sleeps = [2**i for i in range(failures_before_success)]
        assert sleep_calls == expected_sleeps
