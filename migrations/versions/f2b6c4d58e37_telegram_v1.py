"""telegram_v1

Revision ID: f2b6c4d58e37
Revises: e1a5b3c47d26
Create Date: 2026-10-07 16:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2b6c4d58e37"
down_revision: Union[str, Sequence[str], None] = "e1a5b3c47d26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_link_challenges",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(
        op.f("ix_telegram_link_challenges_user_id"), "telegram_link_challenges", ["user_id"]
    )

    op.create_table(
        "telegram_updates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("linked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("handled", sa.String(length=60), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("update_id"),
    )
    op.create_index(
        op.f("ix_telegram_updates_telegram_user_id"), "telegram_updates", ["telegram_user_id"]
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("outbox_event_id", sa.UUID(), nullable=True),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("decision_record_id", sa.UUID(), nullable=True),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=20), server_default="telegram", nullable=False),
        sa.Column("template", sa.String(length=40), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("reply_markup", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("transport", sa.String(length=20), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["signal_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "telegram_chat_id", name="uq_delivery_candidate_chat"),
    )
    op.create_index(
        op.f("ix_notification_deliveries_candidate_id"), "notification_deliveries", ["candidate_id"]
    )
    op.create_index(
        op.f("ix_notification_deliveries_owner_user_id"),
        "notification_deliveries",
        ["owner_user_id"],
    )
    op.create_index(
        op.f("ix_notification_deliveries_status"), "notification_deliveries", ["status"]
    )

    op.create_table(
        "telegram_alert_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["signal_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_telegram_alert_actions_candidate_id"), "telegram_alert_actions", ["candidate_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_telegram_alert_actions_candidate_id"), table_name="telegram_alert_actions")
    op.drop_table("telegram_alert_actions")
    op.drop_index(op.f("ix_notification_deliveries_status"), table_name="notification_deliveries")
    op.drop_index(
        op.f("ix_notification_deliveries_owner_user_id"), table_name="notification_deliveries"
    )
    op.drop_index(
        op.f("ix_notification_deliveries_candidate_id"), table_name="notification_deliveries"
    )
    op.drop_table("notification_deliveries")
    op.drop_index(op.f("ix_telegram_updates_telegram_user_id"), table_name="telegram_updates")
    op.drop_table("telegram_updates")
    op.drop_index(op.f("ix_telegram_link_challenges_user_id"), table_name="telegram_link_challenges")
    op.drop_table("telegram_link_challenges")
