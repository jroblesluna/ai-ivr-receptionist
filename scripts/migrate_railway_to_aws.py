#!/usr/bin/env python3
"""
Data migration script: Railway (SQLite) → AWS (PostgreSQL + Secrets Manager + S3).

Migrates all tables in dependency order, decrypts Fernet-encrypted config values
and stores them in Secrets Manager, uploads report files to S3, and handles
idempotency by skipping existing records.

Usage:
    python scripts/migrate_railway_to_aws.py --source /path/to/app.db

Environment variables:
    DATABASE_URL        - Target PostgreSQL connection string
    SECRET_KEY          - Fernet key used to decrypt _sec_ config values
    AWS_REGION          - AWS region for Secrets Manager and S3
    AWS_SECRET_NAME     - Secrets Manager secret name (e.g. pickup/dev/secrets)
    S3_REPORTS_BUCKET   - S3 bucket name for reports
    REPORTS_DIR         - Path to local reports directory (default: data/reports)

Exit codes:
    0 - All records migrated successfully
    1 - One or more records failed to migrate
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path so we can import src.models
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.models import Base
from src.models.caller_profile import CallerProfile
from src.models.config import Config
from src.models.report import Report
from src.models.use_case import Topic, UseCase
from src.models.user import Role, User, UserUseCase

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Migration order (respects foreign key dependencies) ───────────────────────

MIGRATION_ORDER = [
    "roles",
    "users",
    "use_cases",
    "topics",
    "user_use_cases",
    "caller_profiles",
    "config",
    "reports",
]


# ── Helper: Fernet decryption ─────────────────────────────────────────────────


def decrypt_fernet_value(encrypted_value: str, fernet: Fernet) -> str:
    """Decrypt a Fernet-encrypted value and return the plaintext string."""
    return fernet.decrypt(encrypted_value.encode()).decode()


# ── Helper: Secrets Manager ───────────────────────────────────────────────────


def store_secrets_in_aws(secrets: dict[str, str], region: str, secret_name: str) -> None:
    """Store decrypted secrets in AWS Secrets Manager.

    Merges with existing secret values (does not overwrite unrelated keys).
    """
    import boto3

    client = boto3.client("secretsmanager", region_name=region)

    # Fetch existing secret to merge
    try:
        response = client.get_secret_value(SecretId=secret_name)
        existing = json.loads(response["SecretString"])
    except client.exceptions.ResourceNotFoundException:
        existing = {}
    except Exception as exc:
        logger.warning("Could not fetch existing secret %s: %s", secret_name, exc)
        existing = {}

    # Merge new secrets into existing
    existing.update(secrets)

    # Update the secret
    client.put_secret_value(
        SecretId=secret_name,
        SecretString=json.dumps(existing),
    )
    logger.info(
        "Stored %d decrypted secrets in Secrets Manager (%s)",
        len(secrets),
        secret_name,
    )


# ── Helper: S3 upload ─────────────────────────────────────────────────────────


def upload_report_files_to_s3(
    report_id: str, reports_dir: Path, bucket: str, region: str
) -> tuple[int, int]:
    """Upload report JSON and MP3 files to S3.

    Returns (uploaded_count, failed_count).
    """
    import boto3

    client = boto3.client("s3", region_name=region)
    uploaded = 0
    failed = 0

    # Possible report files: {id}.json, {id}.mp3, {id}.recording.mp3
    file_patterns = [
        (f"{report_id}.json", f"reports/{report_id}.json"),
        (f"{report_id}.mp3", f"reports/{report_id}.mp3"),
        (f"{report_id}.recording.mp3", f"reports/{report_id}.recording.mp3"),
    ]

    for filename, s3_key in file_patterns:
        filepath = reports_dir / filename
        if filepath.exists():
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=s3_key,
                    Body=filepath.read_bytes(),
                )
                uploaded += 1
            except Exception as exc:
                logger.error(
                    "reports | file=%s | Failed to upload to S3: %s",
                    filename,
                    exc,
                )
                failed += 1

    return uploaded, failed


# ── Table migration functions ─────────────────────────────────────────────────


def migrate_roles(source_session, target_session, summary: dict) -> None:
    """Migrate roles table."""
    rows = source_session.execute(text("SELECT id, name FROM roles")).fetchall()
    migrated = 0
    failed = 0

    for row in rows:
        record_id = row[0]
        try:
            existing = target_session.get(Role, record_id)
            if existing:
                continue  # Idempotency: skip existing
            role = Role(id=record_id, name=row[1])
            target_session.add(role)
            target_session.flush()
            migrated += 1
        except Exception as exc:
            target_session.rollback()
            logger.error("roles | id=%s | %s", record_id, exc)
            failed += 1

    target_session.commit()
    summary["roles"] = {"migrated": migrated, "failed": failed}


def migrate_users(source_session, target_session, summary: dict) -> None:
    """Migrate users table."""
    rows = source_session.execute(
        text(
            "SELECT id, first_name, last_name, email, phone, password_hash, "
            "role_id, email_verified, phone_verified, is_active, email_token, "
            "created_at FROM users"
        )
    ).fetchall()
    migrated = 0
    failed = 0

    for row in rows:
        record_id = row[0]
        try:
            existing = target_session.get(User, record_id)
            if existing:
                continue
            user = User(
                id=record_id,
                first_name=row[1],
                last_name=row[2],
                email=row[3],
                phone=row[4],
                password_hash=row[5],
                role_id=row[6],
                email_verified=row[7],
                phone_verified=row[8],
                is_active=row[9],
                email_token=row[10],
                created_at=row[11],
            )
            target_session.add(user)
            target_session.flush()
            migrated += 1
        except Exception as exc:
            target_session.rollback()
            logger.error("users | id=%s | %s", record_id, exc)
            failed += 1

    target_session.commit()
    summary["users"] = {"migrated": migrated, "failed": failed}


def migrate_use_cases(source_session, target_session, summary: dict) -> None:
    """Migrate use_cases table."""
    rows = source_session.execute(
        text(
            "SELECT id, name, industry, url, forward_to, voice_en, voice_es, "
            "slogan_en, slogan_es, is_demo, demo_code, ivr_type, "
            "system_prompt, system_prompt_es, knowledge_base FROM use_cases"
        )
    ).fetchall()
    migrated = 0
    failed = 0

    for row in rows:
        record_id = row[0]
        try:
            existing = target_session.get(UseCase, record_id)
            if existing:
                continue
            uc = UseCase(
                id=record_id,
                name=row[1],
                industry=row[2],
                url=row[3],
                forward_to=row[4],
                voice_en=row[5],
                voice_es=row[6],
                slogan_en=row[7],
                slogan_es=row[8],
                is_demo=row[9],
                demo_code=row[10],
                ivr_type=row[11],
                system_prompt=row[12],
                system_prompt_es=row[13],
                knowledge_base=row[14],
            )
            target_session.add(uc)
            target_session.flush()
            migrated += 1
        except Exception as exc:
            target_session.rollback()
            logger.error("use_cases | id=%s | %s", record_id, exc)
            failed += 1

    target_session.commit()
    summary["use_cases"] = {"migrated": migrated, "failed": failed}


def migrate_topics(source_session, target_session, summary: dict) -> None:
    """Migrate topics table."""
    rows = source_session.execute(
        text(
            "SELECT id, use_case_id, key, digit, meeting_type, label_en, "
            "label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, "
            "system_extra_en, system_extra_es, questions_en, questions_es "
            "FROM topics"
        )
    ).fetchall()
    migrated = 0
    failed = 0

    for row in rows:
        record_id = row[0]
        try:
            existing = target_session.get(Topic, record_id)
            if existing:
                continue
            topic = Topic(
                id=record_id,
                use_case_id=row[1],
                key=row[2],
                digit=row[3],
                meeting_type=row[4],
                label_en=row[5],
                label_es=row[6],
                menu_text_en=row[7],
                menu_text_es=row[8],
                greeting_en=row[9],
                greeting_es=row[10],
                system_extra_en=row[11],
                system_extra_es=row[12],
                questions_en=row[13],
                questions_es=row[14],
            )
            target_session.add(topic)
            target_session.flush()
            migrated += 1
        except Exception as exc:
            target_session.rollback()
            logger.error("topics | id=%s | %s", record_id, exc)
            failed += 1

    target_session.commit()
    summary["topics"] = {"migrated": migrated, "failed": failed}


def migrate_user_use_cases(source_session, target_session, summary: dict) -> None:
    """Migrate user_use_cases table."""
    rows = source_session.execute(
        text("SELECT user_id, use_case_id FROM user_use_cases")
    ).fetchall()
    migrated = 0
    failed = 0

    for row in rows:
        user_id, use_case_id = row[0], row[1]
        try:
            existing = target_session.get(UserUseCase, (user_id, use_case_id))
            if existing:
                continue
            uuc = UserUseCase(user_id=user_id, use_case_id=use_case_id)
            target_session.add(uuc)
            target_session.flush()
            migrated += 1
        except Exception as exc:
            target_session.rollback()
            logger.error(
                "user_use_cases | user_id=%s, use_case_id=%s | %s",
                user_id,
                use_case_id,
                exc,
            )
            failed += 1

    target_session.commit()
    summary["user_use_cases"] = {"migrated": migrated, "failed": failed}


def migrate_caller_profiles(source_session, target_session, summary: dict) -> None:
    """Migrate caller_profiles table."""
    rows = source_session.execute(
        text(
            "SELECT phone, use_case_id, profile_json, updated_at "
            "FROM caller_profiles"
        )
    ).fetchall()
    migrated = 0
    failed = 0

    for row in rows:
        phone, use_case_id = row[0], row[1]
        try:
            existing = target_session.get(CallerProfile, (phone, use_case_id))
            if existing:
                continue
            cp = CallerProfile(
                phone=phone,
                use_case_id=use_case_id,
                profile_json=row[2],
                updated_at=row[3],
            )
            target_session.add(cp)
            target_session.flush()
            migrated += 1
        except Exception as exc:
            target_session.rollback()
            logger.error(
                "caller_profiles | phone=%s, use_case_id=%s | %s",
                phone,
                use_case_id,
                exc,
            )
            failed += 1

    target_session.commit()
    summary["caller_profiles"] = {"migrated": migrated, "failed": failed}


def migrate_config(
    source_session, target_session, summary: dict, fernet: Fernet | None,
    aws_region: str, aws_secret_name: str,
) -> None:
    """Migrate config table.

    Keys prefixed with '_sec_' are Fernet-encrypted. These are decrypted and
    stored in Secrets Manager instead of the target database.
    """
    rows = source_session.execute(
        text("SELECT key, value FROM config")
    ).fetchall()
    migrated = 0
    failed = 0
    secrets_to_store: dict[str, str] = {}

    for row in rows:
        key, value = row[0], row[1]
        try:
            if key.startswith("_sec_") and fernet and value:
                # Decrypt and collect for Secrets Manager
                plain_key = key[5:]  # Remove '_sec_' prefix
                plain_value = decrypt_fernet_value(value, fernet)
                secrets_to_store[plain_key] = plain_value
                migrated += 1
            else:
                # Regular config: store in target DB
                existing = target_session.get(Config, key)
                if existing:
                    continue
                config = Config(key=key, value=value)
                target_session.add(config)
                target_session.flush()
                migrated += 1
        except Exception as exc:
            target_session.rollback()
            logger.error("config | key=%s | %s", key, exc)
            failed += 1

    target_session.commit()

    # Store decrypted secrets in Secrets Manager
    if secrets_to_store and aws_region:
        try:
            store_secrets_in_aws(secrets_to_store, aws_region, aws_secret_name)
        except Exception as exc:
            logger.error(
                "config | Failed to store secrets in Secrets Manager: %s", exc
            )
            failed += len(secrets_to_store)
            migrated -= len(secrets_to_store)

    summary["config"] = {"migrated": migrated, "failed": failed}


def migrate_reports(
    source_session, target_session, summary: dict,
    reports_dir: Path, s3_bucket: str, aws_region: str,
) -> None:
    """Migrate reports table and upload report files to S3."""
    rows = source_session.execute(
        text(
            "SELECT id, datetime, caller_number, caller_name, topic, language "
            "FROM reports"
        )
    ).fetchall()
    migrated = 0
    failed = 0
    files_uploaded = 0
    files_failed = 0

    for row in rows:
        record_id = row[0]
        try:
            existing = target_session.get(Report, record_id)
            if existing:
                # Still try to upload files even if record exists
                if s3_bucket and aws_region and reports_dir.exists():
                    u, f = upload_report_files_to_s3(
                        record_id, reports_dir, s3_bucket, aws_region
                    )
                    files_uploaded += u
                    files_failed += f
                continue

            report = Report(
                id=record_id,
                datetime=row[1],
                caller_number=row[2],
                caller_name=row[3],
                topic=row[4],
                language=row[5],
            )
            target_session.add(report)
            target_session.flush()
            migrated += 1

            # Upload associated files to S3
            if s3_bucket and aws_region and reports_dir.exists():
                u, f = upload_report_files_to_s3(
                    record_id, reports_dir, s3_bucket, aws_region
                )
                files_uploaded += u
                files_failed += f

        except Exception as exc:
            target_session.rollback()
            logger.error("reports | id=%s | %s", record_id, exc)
            failed += 1

    target_session.commit()
    summary["reports"] = {
        "migrated": migrated,
        "failed": failed,
        "files_uploaded": files_uploaded,
        "files_failed": files_failed,
    }


# ── Main migration logic ─────────────────────────────────────────────────────


def run_migration(
    source_db_path: str,
    target_db_url: str,
    secret_key: str | None = None,
    aws_region: str = "",
    aws_secret_name: str = "",
    s3_reports_bucket: str = "",
    reports_dir: str = "",
) -> int:
    """Run the full migration.

    Returns exit code: 0 on full success, 1 if any records failed.
    """
    # ── Connect to source SQLite ──────────────────────────────────────────────
    source_engine = create_engine(f"sqlite:///{source_db_path}")
    SourceSession = sessionmaker(bind=source_engine)
    source_session = SourceSession()

    # Verify source tables exist
    source_inspector = inspect(source_engine)
    source_tables = source_inspector.get_table_names()
    logger.info("Source database tables: %s", source_tables)

    # ── Connect to target PostgreSQL ──────────────────────────────────────────
    target_engine = create_engine(target_db_url)
    TargetSession = sessionmaker(bind=target_engine)
    target_session = TargetSession()

    # Ensure target schema exists
    Base.metadata.create_all(target_engine)
    logger.info("Target database schema ensured.")

    # ── Prepare Fernet cipher ─────────────────────────────────────────────────
    fernet = None
    if secret_key:
        try:
            fernet = Fernet(secret_key.encode() if isinstance(secret_key, str) else secret_key)
        except Exception as exc:
            logger.warning("Invalid SECRET_KEY for Fernet decryption: %s", exc)

    # ── Resolve reports directory ─────────────────────────────────────────────
    reports_path = Path(reports_dir) if reports_dir else PROJECT_ROOT / "data" / "reports"

    # ── Run migrations in dependency order ────────────────────────────────────
    summary: dict[str, dict] = {}

    logger.info("Starting migration...")
    logger.info("=" * 60)

    # roles
    if "roles" in source_tables:
        logger.info("Migrating: roles")
        migrate_roles(source_session, target_session, summary)
    else:
        logger.info("Skipping: roles (table not found in source)")
        summary["roles"] = {"migrated": 0, "failed": 0}

    # users
    if "users" in source_tables:
        logger.info("Migrating: users")
        migrate_users(source_session, target_session, summary)
    else:
        logger.info("Skipping: users (table not found in source)")
        summary["users"] = {"migrated": 0, "failed": 0}

    # use_cases
    if "use_cases" in source_tables:
        logger.info("Migrating: use_cases")
        migrate_use_cases(source_session, target_session, summary)
    else:
        logger.info("Skipping: use_cases (table not found in source)")
        summary["use_cases"] = {"migrated": 0, "failed": 0}

    # topics
    if "topics" in source_tables:
        logger.info("Migrating: topics")
        migrate_topics(source_session, target_session, summary)
    else:
        logger.info("Skipping: topics (table not found in source)")
        summary["topics"] = {"migrated": 0, "failed": 0}

    # user_use_cases
    if "user_use_cases" in source_tables:
        logger.info("Migrating: user_use_cases")
        migrate_user_use_cases(source_session, target_session, summary)
    else:
        logger.info("Skipping: user_use_cases (table not found in source)")
        summary["user_use_cases"] = {"migrated": 0, "failed": 0}

    # caller_profiles
    if "caller_profiles" in source_tables:
        logger.info("Migrating: caller_profiles")
        migrate_caller_profiles(source_session, target_session, summary)
    else:
        logger.info("Skipping: caller_profiles (table not found in source)")
        summary["caller_profiles"] = {"migrated": 0, "failed": 0}

    # config (with Fernet decryption + Secrets Manager)
    if "config" in source_tables:
        logger.info("Migrating: config")
        migrate_config(
            source_session, target_session, summary,
            fernet, aws_region, aws_secret_name,
        )
    else:
        logger.info("Skipping: config (table not found in source)")
        summary["config"] = {"migrated": 0, "failed": 0}

    # reports (with S3 file upload)
    if "reports" in source_tables:
        logger.info("Migrating: reports")
        migrate_reports(
            source_session, target_session, summary,
            reports_path, s3_reports_bucket, aws_region,
        )
    else:
        logger.info("Skipping: reports (table not found in source)")
        summary["reports"] = {"migrated": 0, "failed": 0}

    # ── Close sessions ────────────────────────────────────────────────────────
    source_session.close()
    target_session.close()

    # ── Output summary ────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 60)

    total_migrated = 0
    total_failed = 0

    for table in MIGRATION_ORDER:
        stats = summary.get(table, {"migrated": 0, "failed": 0})
        m = stats["migrated"]
        f = stats["failed"]
        total_migrated += m
        total_failed += f
        extra = ""
        if table == "reports" and "files_uploaded" in stats:
            extra = f" (files: {stats['files_uploaded']} uploaded, {stats['files_failed']} failed)"
            total_failed += stats["files_failed"]
        logger.info("  %-20s migrated=%d  failed=%d%s", table, m, f, extra)

    logger.info("-" * 60)
    logger.info("  TOTAL:              migrated=%d  failed=%d", total_migrated, total_failed)
    logger.info("=" * 60)

    if total_failed > 0:
        logger.warning("Migration completed with %d failures.", total_failed)
        return 1
    else:
        logger.info("Migration completed successfully.")
        return 0


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate data from Railway SQLite to AWS PostgreSQL + S3 + Secrets Manager"
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("SOURCE_DB_PATH", str(PROJECT_ROOT / "data" / "app.db")),
        help="Path to source SQLite database (default: data/app.db or SOURCE_DB_PATH env var)",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("DATABASE_URL", ""),
        help="Target PostgreSQL URL (default: DATABASE_URL env var)",
    )
    parser.add_argument(
        "--reports-dir",
        default=os.environ.get("REPORTS_DIR", ""),
        help="Path to local reports directory (default: data/reports or REPORTS_DIR env var)",
    )
    args = parser.parse_args()

    if not args.target:
        logger.error("Target database URL is required. Set DATABASE_URL or use --target.")
        sys.exit(1)

    source_path = args.source
    if not Path(source_path).exists():
        logger.error("Source database not found: %s", source_path)
        sys.exit(1)

    exit_code = run_migration(
        source_db_path=source_path,
        target_db_url=args.target,
        secret_key=os.environ.get("SECRET_KEY", ""),
        aws_region=os.environ.get("AWS_REGION", ""),
        aws_secret_name=os.environ.get("AWS_SECRET_NAME", "pickup/dev/secrets"),
        s3_reports_bucket=os.environ.get("S3_REPORTS_BUCKET", ""),
        reports_dir=args.reports_dir,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
