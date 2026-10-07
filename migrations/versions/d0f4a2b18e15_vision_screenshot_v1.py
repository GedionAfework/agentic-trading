"""vision_screenshot_v1

Revision ID: d0f4a2b18e15
Revises: c9e3f1a28d04
Create Date: 2026-10-07 14:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d0f4a2b18e15"
down_revision: Union[str, Sequence[str], None] = "c9e3f1a28d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screenshot_jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="analyzed", nullable=False),
        sa.Column("market_symbol", sa.String(length=40), nullable=True),
        sa.Column("market_timeframe", sa.String(length=20), nullable=True),
        sa.Column(
            "extraction",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "verification",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("authorizes_trade", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("corrected_symbol", sa.String(length=40), nullable=True),
        sa.Column("corrected_timeframe", sa.String(length=20), nullable=True),
        sa.Column("corrected_by", sa.UUID(), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_screenshot_jobs_owner_user_id"), "screenshot_jobs", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_screenshot_jobs_owner_user_id"), table_name="screenshot_jobs")
    op.drop_table("screenshot_jobs")
