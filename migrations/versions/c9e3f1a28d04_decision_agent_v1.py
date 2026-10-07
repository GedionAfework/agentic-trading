"""decision_agent_v1

Revision ID: c9e3f1a28d04
Revises: b8d4e2a17c90
Create Date: 2026-10-07 13:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e3f1a28d04"
down_revision: Union[str, Sequence[str], None] = "b8d4e2a17c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("symbol", sa.String(length=40), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        sa.Column("bar_open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("setup_state", sa.String(length=40), nullable=False),
        sa.Column("confidence_band", sa.String(length=20), nullable=False),
        sa.Column("strategy_code", sa.String(length=80), nullable=False),
        sa.Column("strategy_version_no", sa.Integer(), nullable=False),
        sa.Column("risk_approved", sa.Boolean(), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("stop_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("target_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("rr_ratio", sa.Numeric(12, 6), nullable=True),
        sa.Column("model_id", sa.UUID(), nullable=True),
        sa.Column("model_score", sa.Numeric(8, 6), nullable=True),
        sa.Column("model_band", sa.String(length=20), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("explanation_source", sa.String(length=40), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "workflow",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "hard_blockers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
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
    )
    op.create_index(
        op.f("ix_decision_records_owner_user_id"), "decision_records", ["owner_user_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_decision_records_owner_user_id"), table_name="decision_records")
    op.drop_table("decision_records")
