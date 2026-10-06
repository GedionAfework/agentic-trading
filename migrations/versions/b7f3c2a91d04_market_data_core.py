"""market_data_core

Revision ID: b7f3c2a91d04
Revises: c9e2900ba99e
Create Date: 2026-10-06 16:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7f3c2a91d04"
down_revision: Union[str, Sequence[str], None] = "c9e2900ba99e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_providers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column(
            "config",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "instruments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("canonical_symbol", sa.String(length=64), nullable=False),
        sa.Column("asset_class", sa.String(length=24), nullable=False),
        sa.Column("base_asset", sa.String(length=32), nullable=True),
        sa.Column("quote_asset", sa.String(length=32), nullable=True),
        sa.Column("price_tick", sa.Numeric(30, 12), nullable=True),
        sa.Column("qty_step", sa.Numeric(30, 12), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_symbol"),
    )
    op.create_table(
        "provider_symbols",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=64), nullable=False),
        sa.Column(
            "interval_map",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["market_providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "provider_symbol", name="uq_provider_symbol"),
    )
    op.create_index(
        op.f("ix_provider_symbols_instrument_id"), "provider_symbols", ["instrument_id"], unique=False
    )
    op.create_index(
        op.f("ix_provider_symbols_provider_id"), "provider_symbols", ["provider_id"], unique=False
    )
    op.create_table(
        "candles",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(30, 12), nullable=False),
        sa.Column("high", sa.Numeric(30, 12), nullable=False),
        sa.Column("low", sa.Numeric(30, 12), nullable=False),
        sa.Column("close", sa.Numeric(30, 12), nullable=False),
        sa.Column("volume", sa.Numeric(38, 12), nullable=True),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("is_final", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "quality_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["market_providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            "open_time",
            "provider_id",
            name="uq_candle_identity",
        ),
    )
    op.create_index(op.f("ix_candles_instrument_id"), "candles", ["instrument_id"], unique=False)
    op.create_index(op.f("ix_candles_open_time"), "candles", ["open_time"], unique=False)
    op.create_index(op.f("ix_candles_provider_id"), "candles", ["provider_id"], unique=False)
    op.create_index(op.f("ix_candles_timeframe"), "candles", ["timeframe"], unique=False)
    op.create_table(
        "market_data_gaps",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("gap_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gap_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="open", nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_market_data_gaps_instrument_id"),
        "market_data_gaps",
        ["instrument_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_market_data_gaps_instrument_id"), table_name="market_data_gaps")
    op.drop_table("market_data_gaps")
    op.drop_index(op.f("ix_candles_timeframe"), table_name="candles")
    op.drop_index(op.f("ix_candles_provider_id"), table_name="candles")
    op.drop_index(op.f("ix_candles_open_time"), table_name="candles")
    op.drop_index(op.f("ix_candles_instrument_id"), table_name="candles")
    op.drop_table("candles")
    op.drop_index(op.f("ix_provider_symbols_provider_id"), table_name="provider_symbols")
    op.drop_index(op.f("ix_provider_symbols_instrument_id"), table_name="provider_symbols")
    op.drop_table("provider_symbols")
    op.drop_table("instruments")
    op.drop_table("market_providers")
