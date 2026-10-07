"""risk_engine_v1

Revision ID: e5b1c3d84f90
Revises: d4a8e1f02c77
Create Date: 2026-10-06 22:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5b1c3d84f90"
down_revision: Union[str, Sequence[str], None] = "d4a8e1f02c77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_policies",
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
    op.create_index(
        op.f("ix_risk_policies_owner_user_id"), "risk_policies", ["owner_user_id"], unique=False
    )

    op.create_table(
        "risk_policy_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
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
        sa.ForeignKeyConstraint(["policy_id"], ["risk_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "version_no", name="uq_risk_policy_version_no"),
    )
    op.create_index(
        op.f("ix_risk_policy_versions_policy_id"),
        "risk_policy_versions",
        ["policy_id"],
        unique=False,
    )

    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column("setup_id", sa.UUID(), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry_reference", sa.Numeric(30, 12), nullable=True),
        sa.Column("stop_price", sa.Numeric(30, 12), nullable=True),
        sa.Column("target_1", sa.Numeric(30, 12), nullable=True),
        sa.Column("risk_distance", sa.Numeric(30, 12), nullable=True),
        sa.Column("reward_distance", sa.Numeric(30, 12), nullable=True),
        sa.Column("rr_ratio", sa.Numeric(12, 4), nullable=True),
        sa.Column(
            "hard_blockers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("approved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "paper_size",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "input_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"], ["risk_policy_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("setup_id"),
    )
    op.create_index(
        op.f("ix_risk_assessments_policy_version_id"),
        "risk_assessments",
        ["policy_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_risk_assessments_policy_version_id"), table_name="risk_assessments")
    op.drop_table("risk_assessments")
    op.drop_index(op.f("ix_risk_policy_versions_policy_id"), table_name="risk_policy_versions")
    op.drop_table("risk_policy_versions")
    op.drop_index(op.f("ix_risk_policies_owner_user_id"), table_name="risk_policies")
    op.drop_table("risk_policies")
