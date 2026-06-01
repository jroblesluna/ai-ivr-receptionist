"""
Database access layer — delegates to SQLAlchemy models.

Maintains the same public function API so existing route code continues to work.
Schema creation is handled by create_all; connection pooling by SQLAlchemy engine.
"""
import json
import logging
import os
import secrets
import time
from datetime import datetime as _dt
from functools import wraps
from pathlib import Path

from sqlalchemy import create_engine, func as sa_func, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from src.models import Base
    from src.models.caller_profile import CallerProfile
    from src.models.config import Config
    from src.models.report import Report
    from src.models.use_case import Topic, UseCase
    from src.models.user import Role, User, UserUseCase
except ImportError:
    from models import Base
    from models.caller_profile import CallerProfile
    from models.config import Config
    from models.report import Report
    from models.use_case import Topic, UseCase
    from models.user import Role, User, UserUseCase

logger = logging.getLogger(__name__)

# ── Lazy Session factory ──────────────────────────────────────────────────────

_SessionFactory = None


def _get_session_factory():
    """Get or create the SQLAlchemy session factory."""
    global _SessionFactory
    if _SessionFactory is not None:
        return _SessionFactory

    # Try env var first, then SecretsConfig
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        try:
            from config import SecretsConfig
            db_url = SecretsConfig.get("DATABASE_URL", "")
        except Exception:
            pass
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    engine = create_engine(
        db_url,
        pool_size=2,
        max_overflow=8,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    _SessionFactory = sessionmaker(bind=engine)

    # Ensure tables exist on first connection
    Base.metadata.create_all(engine)

    return _SessionFactory


def Session():
    """Create a new database session (lazy initialization)."""
    return _get_session_factory()()
logger = logging.getLogger(__name__)

# ── Connection retry decorator ────────────────────────────────────────────────

MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds


def _with_retry(func):
    """Wrap a database function with exponential backoff retry on OperationalError."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        backoff = INITIAL_BACKOFF
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except OperationalError as e:
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "DB operation %s attempt %d/%d failed: %s. Retrying in %ds...",
                        func.__name__, attempt, MAX_RETRIES, e, backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    logger.error(
                        "DB operation %s failed after %d attempts: %s",
                        func.__name__, MAX_RETRIES, e,
                    )
                    raise
    return wrapper


# ── Config ────────────────────────────────────────────────────────────────────

@_with_retry
def config_get(key: str, default=None):
    with Session() as session:
        row = session.query(Config).filter(Config.key == key).first()
    return row.value if row else default


@_with_retry
def config_set(key: str, value: str):
    with Session() as session:
        existing = session.query(Config).filter(Config.key == key).first()
        if existing:
            existing.value = value
        else:
            session.add(Config(key=key, value=value))
        session.commit()


@_with_retry
def config_all() -> dict:
    with Session() as session:
        rows = session.query(Config).all()
    return {r.key: r.value for r in rows}


@_with_retry
def config_seed(defaults: dict):
    """Insert keys that don't exist yet (used on first boot)."""
    with Session() as session:
        for key, value in defaults.items():
            exists = session.query(Config).filter(Config.key == key).first()
            if not exists:
                session.add(Config(key=key, value=value if value is not None else ""))
        session.commit()


# ── Reports ───────────────────────────────────────────────────────────────────

@_with_retry
def report_insert(report_id: str, data: dict):
    with Session() as session:
        exists = session.query(Report).filter(Report.id == report_id).first()
        if exists:
            return
        report = Report(
            id=report_id,
            datetime=data.get("timestamp", ""),
            caller_number=data.get("caller_phone", ""),
            caller_name=data.get("caller_name", ""),
            topic=data.get("topic", ""),
            language=data.get("language", ""),
        )
        session.add(report)
        session.commit()


@_with_retry
def report_list(limit: int = 50, offset: int = 0) -> list[dict]:
    with Session() as session:
        rows = (
            session.query(Report)
            .order_by(Report.datetime.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
    return [
        {
            "id": r.id,
            "datetime": r.datetime,
            "caller_number": r.caller_number,
            "caller_name": r.caller_name,
            "topic": r.topic,
            "language": r.language,
        }
        for r in rows
    ]


@_with_retry
def report_count() -> int:
    with Session() as session:
        return session.query(sa_func.count(Report.id)).scalar()


def migrate_reports_from_json():
    """Scan existing JSON report files and index any missing records."""
    reports_dir = Path(__file__).parent.parent / "data" / "reports"
    if not reports_dir.exists():
        return
    with Session() as session:
        existing = {r.id for r in session.query(Report.id).all()}
    for path in reports_dir.glob("*.json"):
        report_id = path.stem
        if report_id not in existing:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                report_insert(report_id, data)
            except Exception:
                pass


def migrate_config_from_json():
    """Seed config table from runtime_config_defaults.json (committed in src/).
    Falls back to data/runtime_config.json for backwards compatibility."""
    for json_path in [
        Path(__file__).parent / "runtime_config_defaults.json",
        Path(__file__).parent.parent / "data" / "runtime_config.json",
    ]:
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                config_seed(data)
            except Exception:
                pass
            return


# ── Use Cases ─────────────────────────────────────────────────────────────────

def _uc_to_dict(uc: UseCase) -> dict:
    return {
        "id":               uc.id,
        "name":             uc.name,
        "industry":         uc.industry or "",
        "url":              uc.url or "",
        "forward_to":       uc.forward_to or "",
        "voice":            {"en": uc.voice_en or "", "es": uc.voice_es or ""},
        "slogan":           {"en": uc.slogan_en or "", "es": uc.slogan_es or ""},
        "topics":           {},
        "is_demo":          bool(uc.is_demo),
        "demo_code":        uc.demo_code,
        "ivr_type":         uc.ivr_type or "topics",
        "system_prompt":    uc.system_prompt,
        "system_prompt_es": uc.system_prompt_es,
        "knowledge_base":   uc.knowledge_base,
    }


def _topic_to_dict(t: Topic) -> dict:
    return {
        "digit":        t.digit or "",
        "meeting_type": bool(t.meeting_type),
        "en": {
            "label":        t.label_en or "",
            "menu_text":    t.menu_text_en or "",
            "greeting":     t.greeting_en or "",
            "system_extra": t.system_extra_en or "",
            "questions":    json.loads(t.questions_en or "[]"),
        },
        "es": {
            "label":        t.label_es or "",
            "menu_text":    t.menu_text_es or "",
            "greeting":     t.greeting_es or "",
            "system_extra": t.system_extra_es or "",
            "questions":    json.loads(t.questions_es or "[]"),
        },
    }


@_with_retry
def uc_list(exclude_demos: bool = False) -> dict:
    """Return all use cases with their topics as {id: uc_dict}."""
    with Session() as session:
        query = session.query(UseCase)
        if exclude_demos:
            query = query.filter((UseCase.is_demo == 0) | (UseCase.is_demo.is_(None)))
        uc_rows = query.order_by(UseCase.name).all()
        # Eagerly load topics
        topic_rows = session.query(Topic).order_by(Topic.use_case_id, Topic.digit).all()

    result = {}
    for uc in uc_rows:
        d = _uc_to_dict(uc)
        result[uc.id] = d
    for t in topic_rows:
        if t.use_case_id in result:
            result[t.use_case_id]["topics"][t.key] = _topic_to_dict(t)
    return result


@_with_retry
def uc_get(uc_id: str) -> dict | None:
    with Session() as session:
        uc = session.query(UseCase).filter(UseCase.id == uc_id).first()
        if not uc:
            return None
        d = _uc_to_dict(uc)
        topic_rows = (
            session.query(Topic)
            .filter(Topic.use_case_id == uc_id)
            .order_by(Topic.digit)
            .all()
        )
    for t in topic_rows:
        d["topics"][t.key] = _topic_to_dict(t)
    return d


@_with_retry
def uc_upsert(uc_id: str, data: dict):
    """Save/update a use case and all its topics atomically."""
    v = data.get("voice", {})
    sl = data.get("slogan", {})

    with Session() as session:
        existing = session.query(UseCase).filter(UseCase.id == uc_id).first()

        is_demo = int(data["is_demo"]) if "is_demo" in data else (int(existing.is_demo) if existing and existing.is_demo else 0)
        demo_code = data["demo_code"] if "demo_code" in data else (existing.demo_code if existing else None)
        ivr_type = data["ivr_type"] if "ivr_type" in data else (existing.ivr_type if existing else "topics")
        system_prompt = data["system_prompt"] if "system_prompt" in data else (existing.system_prompt if existing else None)
        system_prompt_es = data["system_prompt_es"] if "system_prompt_es" in data else (existing.system_prompt_es if existing else None)
        knowledge_base = data["knowledge_base"] if "knowledge_base" in data else (existing.knowledge_base if existing else None)

        if existing:
            existing.name = data.get("name", "")
            existing.industry = data.get("industry", "")
            existing.url = data.get("url", "")
            existing.forward_to = data.get("forward_to", "")
            existing.voice_en = v.get("en", "")
            existing.voice_es = v.get("es", "")
            existing.slogan_en = sl.get("en", "")
            existing.slogan_es = sl.get("es", "")
            existing.is_demo = is_demo
            existing.demo_code = demo_code
            existing.ivr_type = ivr_type or "topics"
            existing.system_prompt = system_prompt
            existing.system_prompt_es = system_prompt_es
            existing.knowledge_base = knowledge_base
        else:
            uc = UseCase(
                id=uc_id,
                name=data.get("name", ""),
                industry=data.get("industry", ""),
                url=data.get("url", ""),
                forward_to=data.get("forward_to", ""),
                voice_en=v.get("en", ""),
                voice_es=v.get("es", ""),
                slogan_en=sl.get("en", ""),
                slogan_es=sl.get("es", ""),
                is_demo=is_demo,
                demo_code=demo_code,
                ivr_type=ivr_type or "topics",
                system_prompt=system_prompt,
                system_prompt_es=system_prompt_es,
                knowledge_base=knowledge_base,
            )
            session.add(uc)

        # Replace all topics for this use case
        session.query(Topic).filter(Topic.use_case_id == uc_id).delete()
        for key, t in data.get("topics", {}).items():
            en = t.get("en", {})
            es = t.get("es", {})
            topic = Topic(
                use_case_id=uc_id,
                key=key,
                digit=t.get("digit", ""),
                meeting_type=1 if t.get("meeting_type") else 0,
                label_en=en.get("label", ""),
                label_es=es.get("label", ""),
                menu_text_en=en.get("menu_text", ""),
                menu_text_es=es.get("menu_text", ""),
                greeting_en=en.get("greeting", ""),
                greeting_es=es.get("greeting", ""),
                system_extra_en=en.get("system_extra", ""),
                system_extra_es=es.get("system_extra", ""),
                questions_en=json.dumps(en.get("questions", []), ensure_ascii=False),
                questions_es=json.dumps(es.get("questions", []), ensure_ascii=False),
            )
            session.add(topic)
        session.commit()


@_with_retry
def uc_delete(uc_id: str):
    with Session() as session:
        session.query(Topic).filter(Topic.use_case_id == uc_id).delete()
        session.query(CallerProfile).filter(CallerProfile.use_case_id == uc_id).delete()
        session.query(UseCase).filter(UseCase.id == uc_id).delete()
        session.commit()


@_with_retry
def uc_get_by_demo_code(code: str) -> dict | None:
    """Look up a demo use case by its 6-digit activation code."""
    with Session() as session:
        uc = (
            session.query(UseCase)
            .filter(UseCase.demo_code == code, UseCase.is_demo == 1)
            .first()
        )
        if not uc:
            return None
        d = _uc_to_dict(uc)
        topic_rows = (
            session.query(Topic)
            .filter(Topic.use_case_id == uc.id)
            .order_by(Topic.digit)
            .all()
        )
    for t in topic_rows:
        d["topics"][t.key] = _topic_to_dict(t)
    return d


@_with_retry
def uc_list_demos() -> list[dict]:
    """Return all demo use cases with profile counts."""
    with Session() as session:
        uc_rows = (
            session.query(
                UseCase,
                sa_func.count(CallerProfile.phone).label("profile_count"),
            )
            .outerjoin(CallerProfile, CallerProfile.use_case_id == UseCase.id)
            .filter(UseCase.is_demo == 1)
            .group_by(UseCase.id)
            .order_by(UseCase.name)
            .all()
        )
    result = []
    for uc, profile_count in uc_rows:
        d = _uc_to_dict(uc)
        d["profile_count"] = profile_count
        result.append(d)
    return result


# ── Caller Profiles (demo memory) ─────────────────────────────────────────────

@_with_retry
def caller_profile_get(phone: str, use_case_id: str) -> dict:
    with Session() as session:
        row = (
            session.query(CallerProfile)
            .filter(CallerProfile.phone == phone, CallerProfile.use_case_id == use_case_id)
            .first()
        )
    if not row:
        return {}
    try:
        return json.loads(row.profile_json or "{}")
    except Exception:
        return {}


@_with_retry
def caller_profile_set(phone: str, use_case_id: str, data: dict, updated_at: str = None):
    ts = updated_at or _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    with Session() as session:
        existing = (
            session.query(CallerProfile)
            .filter(CallerProfile.phone == phone, CallerProfile.use_case_id == use_case_id)
            .first()
        )
        if existing:
            existing.profile_json = json.dumps(data, ensure_ascii=False)
            existing.updated_at = ts
        else:
            session.add(CallerProfile(
                phone=phone,
                use_case_id=use_case_id,
                profile_json=json.dumps(data, ensure_ascii=False),
                updated_at=ts,
            ))
        session.commit()


@_with_retry
def caller_profile_list(use_case_id: str) -> list[dict]:
    with Session() as session:
        rows = (
            session.query(CallerProfile)
            .filter(CallerProfile.use_case_id == use_case_id)
            .order_by(CallerProfile.updated_at.desc())
            .all()
        )
    result = []
    for r in rows:
        try:
            profile = json.loads(r.profile_json or "{}")
        except Exception:
            profile = {}
        result.append({"phone": r.phone, "profile": profile, "updated_at": r.updated_at})
    return result


@_with_retry
def caller_profile_delete(phone: str, use_case_id: str):
    with Session() as session:
        session.query(CallerProfile).filter(
            CallerProfile.phone == phone, CallerProfile.use_case_id == use_case_id
        ).delete()
        session.commit()


def migrate_use_cases_from_json():
    """Seed use_cases/topics tables from use_cases.json if the table is empty."""
    with Session() as session:
        count = session.query(sa_func.count(UseCase.id)).scalar()
    if count > 0:
        return
    json_path = Path(__file__).parent / "use_cases.json"
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for uc_id, uc in data.items():
            uc_upsert(uc_id, uc)
    except Exception as e:
        print(f"[DB] migrate_use_cases_from_json error: {e}")


# ── Users / Roles ─────────────────────────────────────────────────────────────

def _user_to_dict(user: User, role_name: str = "") -> dict:
    return {
        "id":             user.id,
        "first_name":     user.first_name,
        "last_name":      user.last_name,
        "email":          user.email,
        "phone":          user.phone or "",
        "role_id":        user.role_id,
        "role":           role_name,
        "email_verified": bool(user.email_verified),
        "phone_verified": bool(user.phone_verified),
        "is_active":      bool(user.is_active),
        "created_at":     user.created_at or "",
    }


@_with_retry
def roles_list() -> list[dict]:
    with Session() as session:
        rows = session.query(Role).order_by(Role.id).all()
    return [{"id": r.id, "name": r.name} for r in rows]


@_with_retry
def user_get(user_id: int) -> dict | None:
    with Session() as session:
        row = (
            session.query(User, Role.name.label("role_name"))
            .join(Role, Role.id == User.role_id)
            .filter(User.id == user_id)
            .first()
        )
    if not row:
        return None
    user, role_name = row
    return _user_to_dict(user, role_name)


@_with_retry
def user_get_by_email(email: str) -> dict | None:
    with Session() as session:
        row = (
            session.query(User, Role.name.label("role_name"))
            .join(Role, Role.id == User.role_id)
            .filter(User.email == email.lower().strip())
            .first()
        )
    if not row:
        return None
    user, role_name = row
    return _user_to_dict(user, role_name)


@_with_retry
def user_get_password_hash(user_id: int) -> str:
    with Session() as session:
        user = session.query(User).filter(User.id == user_id).first()
    return user.password_hash if user else ""


@_with_retry
def user_check_password(email: str, password: str) -> dict | None:
    """Return user dict if credentials are valid, else None."""
    with Session() as session:
        row = (
            session.query(User, Role.name.label("role_name"))
            .join(Role, Role.id == User.role_id)
            .filter(User.email == email.lower().strip())
            .first()
        )
    if not row:
        return None
    user, role_name = row
    if not check_password_hash(user.password_hash, password):
        return None
    return _user_to_dict(user, role_name)


@_with_retry
def user_list() -> list[dict]:
    with Session() as session:
        rows = (
            session.query(User, Role.name.label("role_name"))
            .join(Role, Role.id == User.role_id)
            .order_by(User.created_at.desc())
            .all()
        )
    return [_user_to_dict(user, role_name) for user, role_name in rows]


@_with_retry
def user_create(first_name: str, last_name: str, email: str, phone: str,
                password: str, role_id: int) -> int:
    """Create a new user and return their id. Raises ValueError on duplicate email."""
    token = secrets.token_urlsafe(32)
    pw_hash = generate_password_hash(password)
    with Session() as session:
        try:
            user = User(
                first_name=first_name,
                last_name=last_name,
                email=email.lower().strip(),
                phone=phone,
                password_hash=pw_hash,
                role_id=role_id,
                email_token=token,
            )
            session.add(user)
            session.flush()  # Get the ID
            user_id = user.id
            session.commit()
            return user_id
        except IntegrityError:
            session.rollback()
            raise ValueError("Email already exists")


@_with_retry
def user_update(user_id: int, data: dict):
    """Update editable user fields. Omit keys that should not be changed."""
    with Session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return
        for col in ("first_name", "last_name", "phone", "role_id"):
            if col in data:
                setattr(user, col, data[col])
        if "password" in data and data["password"]:
            user.password_hash = generate_password_hash(data["password"])
        session.commit()


@_with_retry
def user_delete(user_id: int):
    with Session() as session:
        session.query(User).filter(User.id == user_id).delete()
        session.commit()


@_with_retry
def user_set_email_verified(user_id: int):
    with Session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.email_verified = 1
            user.email_token = None
            session.commit()
    _user_activate_if_ready(user_id)


@_with_retry
def user_set_phone_verified(user_id: int):
    with Session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.phone_verified = 1
            session.commit()
    _user_activate_if_ready(user_id)


@_with_retry
def _user_activate_if_ready(user_id: int):
    with Session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if user and user.email_verified and user.phone_verified:
            user.is_active = 1
            session.commit()


@_with_retry
def user_get_by_email_token(token: str) -> dict | None:
    with Session() as session:
        row = (
            session.query(User, Role.name.label("role_name"))
            .join(Role, Role.id == User.role_id)
            .filter(User.email_token == token)
            .first()
        )
    if not row:
        return None
    user, role_name = row
    return _user_to_dict(user, role_name)


@_with_retry
def user_assign_use_cases(user_id: int, uc_ids: list):
    with Session() as session:
        session.query(UserUseCase).filter(UserUseCase.user_id == user_id).delete()
        for uc_id in uc_ids:
            session.add(UserUseCase(user_id=user_id, use_case_id=uc_id))
        session.commit()


@_with_retry
def user_get_use_cases(user_id: int) -> list:
    with Session() as session:
        rows = (
            session.query(UserUseCase.use_case_id)
            .filter(UserUseCase.user_id == user_id)
            .all()
        )
    return [r.use_case_id for r in rows]


@_with_retry
def seed_roles_and_admin():
    """Seed the roles table (admin, manager, standard). Admin user is created via /admin/setup."""
    with Session() as session:
        for name in ("admin", "manager", "standard"):
            exists = session.query(Role).filter(Role.name == name).first()
            if not exists:
                session.add(Role(name=name))
        session.commit()


@_with_retry
def has_users() -> bool:
    with Session() as session:
        return session.query(sa_func.count(User.id)).scalar() > 0


# ── Pending first-admin setup (not yet in users table) ────────────────────────

def pending_setup_save(data: dict):
    """Store first-admin form data temporarily until email is verified."""
    config_set("_pending_setup", json.dumps(data))


def pending_setup_get() -> dict | None:
    raw = config_get("_pending_setup")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def pending_setup_get_by_token(token: str) -> dict | None:
    data = pending_setup_get()
    if data and data.get("token") == token:
        return data
    return None


@_with_retry
def pending_setup_clear():
    with Session() as session:
        session.query(Config).filter(Config.key == "_pending_setup").delete()
        session.commit()


# ── Backward-compatibility shims (deprecated — secrets now in AWS Secrets Manager) ──

def config_set_secure(key: str, value: str):
    """Deprecated — use Secrets Manager instead. Kept as no-op for compatibility."""
    pass


def config_get_secure(key: str, default: str = "") -> str:
    """Deprecated — use SecretsConfig.get() instead. Returns empty string."""
    return default


def init():
    """No-op — schema creation is now handled by Alembic migrations."""
    pass
