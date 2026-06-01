# Feature: aws-migration, Property 6: Migration idempotency
"""
Property-based test for migration idempotency.

For any valid dataset, running the migration script twice against the same target
database should produce the same final state as running it once — no duplicate
records, no changed values, and identical record counts.

**Validates: Requirements 9.7**
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import Base
from src.models.config import Config
from src.models.report import Report
from src.models.use_case import UseCase, Topic
from src.models.user import Role, User, UserUseCase
from src.models.caller_profile import CallerProfile
from scripts.migrate_railway_to_aws import run_migration


# ── Strategies ────────────────────────────────────────────────────────────────

safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=50,
)

safe_text_short = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
    max_size=30,
)

safe_text_id = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-",
    ),
    min_size=1,
    max_size=16,
)

# Strategy for a unique email address
email_strategy = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    local=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="._-"),
        min_size=1,
        max_size=15,
    ),
    domain=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=10,
    ),
)


@st.composite
def dataset_strategy(draw):
    """Generate a complete, consistent dataset for migration testing.

    Produces roles, use_cases, users (with valid role_id references),
    config entries, and reports. Ensures referential integrity.
    """
    # Generate 1-3 roles with unique names
    num_roles = draw(st.integers(min_value=1, max_value=3))
    role_names = draw(
        st.lists(safe_text_short, min_size=num_roles, max_size=num_roles, unique=True)
    )
    roles = [{"id": i + 1, "name": name} for i, name in enumerate(role_names)]

    # Generate 1-3 use cases with unique IDs
    num_use_cases = draw(st.integers(min_value=1, max_value=3))
    use_case_ids = draw(
        st.lists(safe_text_id, min_size=num_use_cases, max_size=num_use_cases, unique=True)
    )
    use_cases = []
    for uc_id in use_case_ids:
        use_cases.append({
            "id": uc_id,
            "name": draw(safe_text_short),
            "industry": draw(st.one_of(safe_text, st.none())),
            "url": draw(st.one_of(safe_text, st.none())),
            "forward_to": draw(st.one_of(safe_text, st.none())),
            "voice_en": draw(st.one_of(safe_text, st.none())),
            "voice_es": draw(st.one_of(safe_text, st.none())),
            "slogan_en": draw(st.one_of(safe_text, st.none())),
            "slogan_es": draw(st.one_of(safe_text, st.none())),
            "is_demo": draw(st.integers(min_value=0, max_value=1)),
            "demo_code": draw(st.one_of(safe_text, st.none())),
            "ivr_type": draw(st.sampled_from(["topics", "direct", "menu"])),
        })

    # Generate 0-3 config entries with unique keys
    num_configs = draw(st.integers(min_value=0, max_value=3))
    config_keys = draw(
        st.lists(safe_text_short, min_size=num_configs, max_size=num_configs, unique=True)
    )
    configs = [{"key": k, "value": draw(st.one_of(safe_text, st.none()))} for k in config_keys]

    # Generate 0-3 reports with unique IDs
    num_reports = draw(st.integers(min_value=0, max_value=3))
    report_ids = draw(
        st.lists(safe_text_id, min_size=num_reports, max_size=num_reports, unique=True)
    )
    reports = []
    for rid in report_ids:
        reports.append({
            "id": rid,
            "datetime": draw(safe_text),
            "caller_number": draw(safe_text),
            "caller_name": draw(safe_text),
            "topic": draw(safe_text),
            "language": draw(safe_text),
        })

    # Generate 0-2 users with unique emails and valid role_id references
    num_users = draw(st.integers(min_value=0, max_value=2))
    user_emails = draw(
        st.lists(email_strategy, min_size=num_users, max_size=num_users, unique=True)
    )
    users = []
    for i, email in enumerate(user_emails):
        role_id = draw(st.sampled_from([r["id"] for r in roles]))
        users.append({
            "id": i + 1,
            "first_name": draw(safe_text_short),
            "last_name": draw(safe_text_short),
            "email": email,
            "phone": draw(st.one_of(safe_text, st.none())),
            "password_hash": draw(safe_text_short),
            "role_id": role_id,
            "email_verified": draw(st.integers(min_value=0, max_value=1)),
            "phone_verified": draw(st.integers(min_value=0, max_value=1)),
            "is_active": draw(st.integers(min_value=0, max_value=1)),
            "email_token": draw(st.one_of(safe_text, st.none())),
            "created_at": draw(safe_text),
        })

    return {
        "roles": roles,
        "use_cases": use_cases,
        "configs": configs,
        "reports": reports,
        "users": users,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def create_source_db(db_path: str, dataset: dict) -> None:
    """Create a source SQLite database populated with the given dataset."""
    engine = create_engine(f"sqlite:///{db_path}")

    # Create tables matching what the migration script expects (raw SQL for source)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
                password_hash TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                email_verified INTEGER DEFAULT 0,
                phone_verified INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                email_token TEXT,
                created_at TEXT,
                FOREIGN KEY (role_id) REFERENCES roles(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS use_cases (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                industry TEXT,
                url TEXT,
                forward_to TEXT,
                voice_en TEXT,
                voice_es TEXT,
                slogan_en TEXT,
                slogan_es TEXT,
                is_demo INTEGER DEFAULT 0,
                demo_code TEXT,
                ivr_type TEXT DEFAULT 'topics',
                system_prompt TEXT,
                system_prompt_es TEXT,
                knowledge_base TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY,
                use_case_id TEXT NOT NULL,
                key TEXT NOT NULL,
                digit TEXT,
                meeting_type INTEGER DEFAULT 0,
                label_en TEXT,
                label_es TEXT,
                menu_text_en TEXT,
                menu_text_es TEXT,
                greeting_en TEXT,
                greeting_es TEXT,
                system_extra_en TEXT,
                system_extra_es TEXT,
                questions_en TEXT DEFAULT '[]',
                questions_es TEXT DEFAULT '[]',
                FOREIGN KEY (use_case_id) REFERENCES use_cases(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_use_cases (
                user_id INTEGER NOT NULL,
                use_case_id TEXT NOT NULL,
                PRIMARY KEY (user_id, use_case_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (use_case_id) REFERENCES use_cases(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS caller_profiles (
                phone TEXT NOT NULL,
                use_case_id TEXT NOT NULL,
                profile_json TEXT DEFAULT '{}',
                updated_at TEXT,
                PRIMARY KEY (phone, use_case_id),
                FOREIGN KEY (use_case_id) REFERENCES use_cases(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                datetime TEXT,
                caller_number TEXT,
                caller_name TEXT,
                topic TEXT,
                language TEXT
            )
        """))
        conn.commit()

    # Insert data
    with engine.connect() as conn:
        for role in dataset["roles"]:
            conn.execute(
                text("INSERT INTO roles (id, name) VALUES (:id, :name)"),
                role,
            )

        for user in dataset["users"]:
            conn.execute(
                text(
                    "INSERT INTO users (id, first_name, last_name, email, phone, "
                    "password_hash, role_id, email_verified, phone_verified, "
                    "is_active, email_token, created_at) "
                    "VALUES (:id, :first_name, :last_name, :email, :phone, "
                    ":password_hash, :role_id, :email_verified, :phone_verified, "
                    ":is_active, :email_token, :created_at)"
                ),
                user,
            )

        for uc in dataset["use_cases"]:
            conn.execute(
                text(
                    "INSERT INTO use_cases (id, name, industry, url, forward_to, "
                    "voice_en, voice_es, slogan_en, slogan_es, is_demo, demo_code, "
                    "ivr_type) VALUES (:id, :name, :industry, :url, :forward_to, "
                    ":voice_en, :voice_es, :slogan_en, :slogan_es, :is_demo, "
                    ":demo_code, :ivr_type)"
                ),
                uc,
            )

        for cfg in dataset["configs"]:
            conn.execute(
                text("INSERT INTO config (key, value) VALUES (:key, :value)"),
                cfg,
            )

        for report in dataset["reports"]:
            conn.execute(
                text(
                    "INSERT INTO reports (id, datetime, caller_number, caller_name, "
                    "topic, language) VALUES (:id, :datetime, :caller_number, "
                    ":caller_name, :topic, :language)"
                ),
                report,
            )

        conn.commit()

    engine.dispose()


def get_table_state(target_db_url: str) -> dict:
    """Capture the full state of the target database: counts and all row data."""
    engine = create_engine(target_db_url)
    state = {}

    with engine.connect() as conn:
        # Roles
        rows = conn.execute(text("SELECT id, name FROM roles ORDER BY id")).fetchall()
        state["roles"] = {"count": len(rows), "rows": [dict(r._mapping) for r in rows]}

        # Users
        rows = conn.execute(
            text(
                "SELECT id, first_name, last_name, email, phone, password_hash, "
                "role_id, email_verified, phone_verified, is_active, email_token, "
                "created_at FROM users ORDER BY id"
            )
        ).fetchall()
        state["users"] = {"count": len(rows), "rows": [dict(r._mapping) for r in rows]}

        # Use cases
        rows = conn.execute(
            text(
                "SELECT id, name, industry, url, forward_to, voice_en, voice_es, "
                "slogan_en, slogan_es, is_demo, demo_code, ivr_type FROM use_cases "
                "ORDER BY id"
            )
        ).fetchall()
        state["use_cases"] = {"count": len(rows), "rows": [dict(r._mapping) for r in rows]}

        # Config
        rows = conn.execute(
            text("SELECT key, value FROM config ORDER BY key")
        ).fetchall()
        state["config"] = {"count": len(rows), "rows": [dict(r._mapping) for r in rows]}

        # Reports
        rows = conn.execute(
            text(
                "SELECT id, datetime, caller_number, caller_name, topic, language "
                "FROM reports ORDER BY id"
            )
        ).fetchall()
        state["reports"] = {"count": len(rows), "rows": [dict(r._mapping) for r in rows]}

    engine.dispose()
    return state


# ── Property Test ─────────────────────────────────────────────────────────────


class TestMigrationIdempotency:
    """Property 6: Migration idempotency.

    For any valid dataset, running the migration script twice against the same
    target database should produce the same final state as running it once —
    no duplicate records, no changed values, and identical record counts.

    **Validates: Requirements 9.7**
    """

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    @given(dataset=dataset_strategy())
    def test_migration_idempotency(self, dataset, tmp_path_factory):
        """Running migration twice produces the same state as running it once."""
        # Create temporary files for source and target databases
        tmp_dir = tmp_path_factory.mktemp("migration")
        source_path = str(tmp_dir / "source.db")
        target_path = str(tmp_dir / "target.db")
        target_url = f"sqlite:///{target_path}"

        # Step 1: Create source database with generated data
        create_source_db(source_path, dataset)

        # Step 2: Run migration the first time
        exit_code_1 = run_migration(
            source_db_path=source_path,
            target_db_url=target_url,
            secret_key=None,
            aws_region="",
            aws_secret_name="",
            s3_reports_bucket="",
            reports_dir="",
        )

        # Migration should succeed (exit code 0)
        assert exit_code_1 == 0, f"First migration failed with exit code {exit_code_1}"

        # Step 3: Capture state after first migration
        state_after_first = get_table_state(target_url)

        # Step 4: Run migration a second time (same source, same target)
        exit_code_2 = run_migration(
            source_db_path=source_path,
            target_db_url=target_url,
            secret_key=None,
            aws_region="",
            aws_secret_name="",
            s3_reports_bucket="",
            reports_dir="",
        )

        # Second migration should also succeed
        assert exit_code_2 == 0, f"Second migration failed with exit code {exit_code_2}"

        # Step 5: Capture state after second migration
        state_after_second = get_table_state(target_url)

        # Step 6: Verify idempotency — states must be identical
        for table in ["roles", "users", "use_cases", "config", "reports"]:
            # Same record counts
            assert state_after_first[table]["count"] == state_after_second[table]["count"], (
                f"Table '{table}' record count changed: "
                f"{state_after_first[table]['count']} → {state_after_second[table]['count']}"
            )

            # Same row data (no duplicates, no changed values)
            assert state_after_first[table]["rows"] == state_after_second[table]["rows"], (
                f"Table '{table}' data changed between first and second migration run"
            )
