"""analytics_v1

Revision ID: b4d8f0a23c56
Revises: a3c7e9f12b45
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4d8f0a23c56"
down_revision: Union[str, Sequence[str], None] = "a3c7e9f12b45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "performance_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort", sa.String(length=20), nullable=False),
        sa.Column("grain", sa.String(length=40), server_default="slice", nullable=False),
        sa.Column("strategy_code", sa.String(length=80), server_default="*", nullable=False),
        sa.Column("instrument_symbol", sa.String(length=40), server_default="*", nullable=False),
        sa.Column("timeframe", sa.String(length=12), server_default="*", nullable=False),
        sa.Column("session_bucket", sa.String(length=20), server_default="*", nullable=False),
        sa.Column("sample_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sample_status", sa.String(length=40), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "cohort",
            "strategy_code",
            "instrument_symbol",
            "timeframe",
            "session_bucket",
            "grain",
            name="uq_performance_snapshot_grain",
        ),
    )
    op.create_index("ix_performance_snapshots_owner_user_id", "performance_snapshots", ["owner_user_id"])
    op.create_index("ix_performance_snapshots_cohort", "performance_snapshots", ["cohort"])

    op.create_table(
        "feedback_review_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_review_items_owner_user_id", "feedback_review_items", ["owner_user_id"])
    op.create_index("ix_feedback_review_items_candidate_id", "feedback_review_items", ["candidate_id"])

    op.create_table(
        "calibration_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort", sa.String(length=20), nullable=False),
        sa.Column("band_field", sa.String(length=40), nullable=False),
        sa.Column("sample_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sample_status", sa.String(length=40), nullable=False),
        sa.Column("bands", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("drift_flags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "cohort",
            "band_field",
            name="uq_calibration_snapshot_cohort_band",
        ),
    )
    op.create_index("ix_calibration_snapshots_owner_user_id", "calibration_snapshots", ["owner_user_id"])
    op.create_index("ix_calibration_snapshots_cohort", "calibration_snapshots", ["cohort"])

    op.create_table(
        "retrain_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_model_code", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("evaluation", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resulting_model_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retrain_requests_owner_user_id", "retrain_requests", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_retrain_requests_owner_user_id", table_name="retrain_requests")
    op.drop_table("retrain_requests")
    op.drop_index("ix_calibration_snapshots_cohort", table_name="calibration_snapshots")
    op.drop_index("ix_calibration_snapshots_owner_user_id", table_name="calibration_snapshots")
    op.drop_table("calibration_snapshots")
    op.drop_index("ix_feedback_review_items_candidate_id", table_name="feedback_review_items")
    op.drop_index("ix_feedback_review_items_owner_user_id", table_name="feedback_review_items")
    op.drop_table("feedback_review_items")
    op.drop_index("ix_performance_snapshots_cohort", table_name="performance_snapshots")
    op.drop_index("ix_performance_snapshots_owner_user_id", table_name="performance_snapshots")
    op.drop_table("performance_snapshots")
