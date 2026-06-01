"""Initial schema — full PostgreSQL DDL for PickUp AI IVR Receptionist.

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── config table ──────────────────────────────────────────────────────
    op.create_table(
        "config",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
    )

    # ── reports table ─────────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("datetime", sa.String()),
        sa.Column("caller_number", sa.String()),
        sa.Column("caller_name", sa.String()),
        sa.Column("topic", sa.String()),
        sa.Column("language", sa.String()),
    )

    # ── use_cases table ───────────────────────────────────────────────────
    op.create_table(
        "use_cases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("industry", sa.String()),
        sa.Column("url", sa.String()),
        sa.Column("forward_to", sa.String()),
        sa.Column("voice_en", sa.String()),
        sa.Column("voice_es", sa.String()),
        sa.Column("slogan_en", sa.String()),
        sa.Column("slogan_es", sa.String()),
        sa.Column("is_demo", sa.Integer(), server_default="0"),
        sa.Column("demo_code", sa.String()),
        sa.Column("ivr_type", sa.String(), server_default="topics"),
        sa.Column("system_prompt", sa.Text()),
        sa.Column("system_prompt_es", sa.Text()),
        sa.Column("knowledge_base", sa.Text()),
    )

    # ── topics table ──────────────────────────────────────────────────────
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "use_case_id",
            sa.String(),
            sa.ForeignKey("use_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("digit", sa.String()),
        sa.Column("meeting_type", sa.Integer(), server_default="0"),
        sa.Column("label_en", sa.String()),
        sa.Column("label_es", sa.String()),
        sa.Column("menu_text_en", sa.String()),
        sa.Column("menu_text_es", sa.String()),
        sa.Column("greeting_en", sa.String()),
        sa.Column("greeting_es", sa.String()),
        sa.Column("system_extra_en", sa.String()),
        sa.Column("system_extra_es", sa.String()),
        sa.Column("questions_en", sa.Text(), server_default="[]"),
        sa.Column("questions_es", sa.Text(), server_default="[]"),
        sa.UniqueConstraint("use_case_id", "key", name="uq_topic_use_case_key"),
    )

    # ── roles table ───────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), unique=True, nullable=False),
    )

    # ── users table ───────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), unique=True, nullable=False),
        sa.Column("phone", sa.String()),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id"),
            nullable=False,
        ),
        sa.Column("email_verified", sa.Integer(), server_default="0"),
        sa.Column("phone_verified", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Integer(), server_default="0"),
        sa.Column("email_token", sa.String()),
        sa.Column("created_at", sa.String(), server_default=sa.text("now()")),
    )

    # ── user_use_cases table ──────────────────────────────────────────────
    op.create_table(
        "user_use_cases",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "use_case_id",
            sa.String(),
            sa.ForeignKey("use_cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ── caller_profiles table ─────────────────────────────────────────────
    op.create_table(
        "caller_profiles",
        sa.Column("phone", sa.String(), primary_key=True),
        sa.Column(
            "use_case_id",
            sa.String(),
            sa.ForeignKey("use_cases.id"),
            primary_key=True,
        ),
        sa.Column("profile_json", sa.Text(), server_default="{}"),
        sa.Column("updated_at", sa.String()),
    )


def downgrade() -> None:
    op.drop_table("caller_profiles")
    op.drop_table("user_use_cases")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("topics")
    op.drop_table("use_cases")
    op.drop_table("reports")
    op.drop_table("config")
