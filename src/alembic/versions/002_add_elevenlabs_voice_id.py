"""Add elevenlabs_voice_id column to use_cases table.

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "use_cases",
        sa.Column("elevenlabs_voice_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("use_cases", "elevenlabs_voice_id")
