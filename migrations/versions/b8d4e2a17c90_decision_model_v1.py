"""decision_model_v1

Revision ID: b8d4e2a17c90
Revises: a1b2c3d4e5f6
Create Date: 2026-10-07 13:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8d4e2a17c90"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_models",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("algorithm", sa.String(length=40), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=20), server_default="shadow", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="trained", nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("training_dataset_version_id", sa.UUID(), nullable=True),
        sa.Column(
            "feature_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "training_window",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "feature_importance",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "hyperparameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["training_dataset_version_id"],
            ["training_dataset_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_decision_model_fingerprint"),
    )
    op.create_index(
        op.f("ix_decision_models_owner_user_id"), "decision_models", ["owner_user_id"]
    )
    op.create_index(op.f("ix_decision_models_code"), "decision_models", ["code"])


def downgrade() -> None:
    op.drop_index(op.f("ix_decision_models_code"), table_name="decision_models")
    op.drop_index(op.f("ix_decision_models_owner_user_id"), table_name="decision_models")
    op.drop_table("decision_models")
