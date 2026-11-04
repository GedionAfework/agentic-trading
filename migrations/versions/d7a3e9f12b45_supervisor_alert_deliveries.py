"""supervisor alert deliveries: notification_deliveries.candidate_id nullable

Supervisor/ops alerts are not tied to a signal candidate. The
(candidate_id, telegram_chat_id) unique constraint still dedupes setup
alerts; NULL candidate rows are deduped by outbox event instead.

Revision ID: d7a3e9f12b45
Revises: c5e9a1b34d67
Create Date: 2026-11-03
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7a3e9f12b45"
down_revision: Union[str, Sequence[str], None] = "c5e9a1b34d67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "notification_deliveries",
        "candidate_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM notification_deliveries WHERE candidate_id IS NULL")
    op.alter_column(
        "notification_deliveries",
        "candidate_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
