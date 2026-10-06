"""strategy_engine_v1

Revision ID: d4a8e1f02c77
Revises: b7f3c2a91d04
Create Date: 2026-10-06 21:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4a8e1f02c77"
down_revision: Union[str, Sequence[str], None] = "b7f3c2a91d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_strategies_owner_user_id"), "strategies", ["owner_user_id"], unique=False)

    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("strategy_id", sa.UUID(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("direction_mode", sa.String(length=20), server_default="both", nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id", "version_no", name="uq_strategy_version_no"),
    )
    op.create_index(
        op.f("ix_strategy_versions_strategy_id"), "strategy_versions", ["strategy_id"], unique=False
    )

    op.create_table(
        "strategy_rules",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("strategy_version_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("expression", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("required", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("weight", sa.Numeric(8, 3), server_default="0", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("gate_group", sa.String(length=40), server_default="hard", nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["strategy_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_version_id", "code", name="uq_strategy_rule_code"),
    )
    op.create_index(
        op.f("ix_strategy_rules_strategy_version_id"),
        "strategy_rules",
        ["strategy_version_id"],
        unique=False,
    )

    op.create_table(
        "strategy_scopes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("strategy_version_id", sa.UUID(), nullable=False),
        sa.Column("asset_class", sa.String(length=24), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("timeframe", sa.String(length=12), nullable=True),
        sa.Column("session", sa.String(length=40), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["strategy_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_strategy_scopes_strategy_version_id"),
        "strategy_scopes",
        ["strategy_version_id"],
        unique=False,
    )

    op.create_table(
        "strategy_test_cases",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("strategy_version_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column(
            "input_features",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "input_context",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("expected_setup_state", sa.String(length=40), nullable=False),
        sa.Column(
            "expected_rule_results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["strategy_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_version_id", "code", name="uq_strategy_test_code"),
    )
    op.create_index(
        op.f("ix_strategy_test_cases_strategy_version_id"),
        "strategy_test_cases",
        ["strategy_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_test_cases_strategy_version_id"), table_name="strategy_test_cases")
    op.drop_table("strategy_test_cases")
    op.drop_index(op.f("ix_strategy_scopes_strategy_version_id"), table_name="strategy_scopes")
    op.drop_table("strategy_scopes")
    op.drop_index(op.f("ix_strategy_rules_strategy_version_id"), table_name="strategy_rules")
    op.drop_table("strategy_rules")
    op.drop_index(op.f("ix_strategy_versions_strategy_id"), table_name="strategy_versions")
    op.drop_table("strategy_versions")
    op.drop_index(op.f("ix_strategies_owner_user_id"), table_name="strategies")
    op.drop_table("strategies")
