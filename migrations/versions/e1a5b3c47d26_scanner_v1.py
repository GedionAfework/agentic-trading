"""scanner_v1

Revision ID: e1a5b3c47d26
Revises: d0f4a2b18e15
Create Date: 2026-10-07 16:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a5b3c47d26"
down_revision: Union[str, Sequence[str], None] = "d0f4a2b18e15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("instrument_symbol", sa.String(length=40), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("candle_open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=True),
        sa.Column("setup_state", sa.String(length=40), nullable=True),
        sa.Column("fresh", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("actionable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=True),
        sa.Column("candidate_new", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "details",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_symbol", "timeframe", "candle_open_time", name="uq_scan_run_candle"
        ),
    )
    op.create_index(op.f("ix_scan_runs_instrument_symbol"), "scan_runs", ["instrument_symbol"])
    op.create_index(op.f("ix_scan_runs_created_at"), "scan_runs", ["created_at"])

    op.create_table(
        "signal_candidates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("strategy_code", sa.String(length=80), nullable=False),
        sa.Column("strategy_version_no", sa.Integer(), nullable=False),
        sa.Column("instrument_symbol", sa.String(length=40), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("setup_anchor", sa.String(length=80), nullable=False),
        sa.Column("signal_type", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("candle_open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_record_id", sa.UUID(), nullable=True),
        sa.Column("publish_state", sa.String(length=32), nullable=False),
        sa.Column("seen_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        op.f("ix_signal_candidates_owner_user_id"), "signal_candidates", ["owner_user_id"]
    )
    op.create_index(
        op.f("ix_signal_candidates_instrument_symbol"), "signal_candidates", ["instrument_symbol"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_signal_candidates_instrument_symbol"), table_name="signal_candidates")
    op.drop_index(op.f("ix_signal_candidates_owner_user_id"), table_name="signal_candidates")
    op.drop_table("signal_candidates")
    op.drop_index(op.f("ix_scan_runs_created_at"), table_name="scan_runs")
    op.drop_index(op.f("ix_scan_runs_instrument_symbol"), table_name="scan_runs")
    op.drop_table("scan_runs")
