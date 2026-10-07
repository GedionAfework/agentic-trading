"""backtest_engine_v1

Revision ID: f6c2d9e15a81
Revises: e5b1c3d84f90
Create Date: 2026-10-07 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6c2d9e15a81"
down_revision: Union[str, Sequence[str], None] = "e5b1c3d84f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtest_datasets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("source", sa.String(length=40), server_default="fixture", nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("bar_count", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("bars_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
        sa.UniqueConstraint("owner_user_id", "code", name="uq_backtest_dataset_code"),
    )
    op.create_index(
        op.f("ix_backtest_datasets_owner_user_id"),
        "backtest_datasets",
        ["owner_user_id"],
        unique=False,
    )

    op.create_table(
        "backtest_jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("strategy_code", sa.String(length=80), nullable=False),
        sa.Column("strategy_version_no", sa.Integer(), nullable=False),
        sa.Column("risk_policy_code", sa.String(length=80), nullable=False),
        sa.Column("risk_policy_version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("feature_engine_version", sa.String(length=64), nullable=False),
        sa.Column("strategy_engine_version", sa.String(length=64), nullable=False),
        sa.Column("risk_engine_version", sa.String(length=64), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["backtest_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_backtest_jobs_dataset_id"), "backtest_jobs", ["dataset_id"], unique=False
    )
    op.create_index(
        op.f("ix_backtest_jobs_owner_user_id"), "backtest_jobs", ["owner_user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_backtest_jobs_owner_user_id"), table_name="backtest_jobs")
    op.drop_index(op.f("ix_backtest_jobs_dataset_id"), table_name="backtest_jobs")
    op.drop_table("backtest_jobs")
    op.drop_index(op.f("ix_backtest_datasets_owner_user_id"), table_name="backtest_datasets")
    op.drop_table("backtest_datasets")
