"""paper_v1

Revision ID: a3c7e9f12b45
Revises: f2b6c4d58e37
Create Date: 2026-10-08 06:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3c7e9f12b45"
down_revision: Union[str, Sequence[str], None] = "f2b6c4d58e37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=40), server_default="PAPER", nullable=False),
        sa.Column("currency", sa.String(length=12), server_default="USDT", nullable=False),
        sa.Column("starting_equity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("equity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "fill_model",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("soak_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("soak_days_required", sa.Integer(), server_default="14", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "label", name="uq_paper_account_owner_label"),
    )
    op.create_index(op.f("ix_paper_accounts_owner_user_id"), "paper_accounts", ["owner_user_id"])

    op.create_table(
        "paper_trades",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("decision_record_id", sa.UUID(), nullable=True),
        sa.Column("candidate_id", sa.UUID(), nullable=True),
        sa.Column("instrument_symbol", sa.String(length=40), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=20), server_default="PAPER", nullable=False),
        sa.Column("signal_bar_open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_entry", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("stop_price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("invalidation_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("qty", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("risk_amount", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "fill_model",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("entry_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("entry_bar_open_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("exit_bar_open_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", sa.String(length=60), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("realized_r", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("costs", sa.Numeric(precision=20, scale=8), server_default="0", nullable=False),
        sa.Column("bars_held", sa.Integer(), server_default="0", nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["paper_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_trades_account_id"), "paper_trades", ["account_id"])
    op.create_index(op.f("ix_paper_trades_owner_user_id"), "paper_trades", ["owner_user_id"])
    op.create_index(
        op.f("ix_paper_trades_decision_record_id"), "paper_trades", ["decision_record_id"]
    )
    op.create_index(op.f("ix_paper_trades_instrument_symbol"), "paper_trades", ["instrument_symbol"])
    op.create_index(op.f("ix_paper_trades_status"), "paper_trades", ["status"])

    op.create_table(
        "paper_trade_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("trade_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("bar_open_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["trade_id"], ["paper_trades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_trade_events_trade_id"), "paper_trade_events", ["trade_id"])

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("paper_trade_id", sa.UUID(), nullable=True),
        sa.Column("cohort", sa.String(length=20), server_default="paper", nullable=False),
        sa.Column("instrument_symbol", sa.String(length=40), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("realized_r", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_trade_id"], ["paper_trades.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_trade_id"),
    )
    op.create_index(op.f("ix_journal_entries_owner_user_id"), "journal_entries", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_journal_entries_owner_user_id"), table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_index(op.f("ix_paper_trade_events_trade_id"), table_name="paper_trade_events")
    op.drop_table("paper_trade_events")
    op.drop_index(op.f("ix_paper_trades_status"), table_name="paper_trades")
    op.drop_index(op.f("ix_paper_trades_instrument_symbol"), table_name="paper_trades")
    op.drop_index(op.f("ix_paper_trades_decision_record_id"), table_name="paper_trades")
    op.drop_index(op.f("ix_paper_trades_owner_user_id"), table_name="paper_trades")
    op.drop_index(op.f("ix_paper_trades_account_id"), table_name="paper_trades")
    op.drop_table("paper_trades")
    op.drop_index(op.f("ix_paper_accounts_owner_user_id"), table_name="paper_accounts")
    op.drop_table("paper_accounts")
