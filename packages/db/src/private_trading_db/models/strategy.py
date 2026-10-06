from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from private_trading_db.base import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    versions: Mapped[list[StrategyVersion]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version_no", name="uq_strategy_version_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    direction_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default="both")
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    strategy: Mapped[Strategy] = relationship(back_populates="versions")
    rules: Mapped[list[StrategyRule]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="StrategyRule.sort_order"
    )
    scopes: Mapped[list[StrategyScope]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    test_cases: Mapped[list[StrategyTestCase]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class StrategyRule(Base):
    __tablename__ = "strategy_rules"
    __table_args__ = (
        UniqueConstraint("strategy_version_id", "code", name="uq_strategy_rule_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    expression: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, server_default="0")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    gate_group: Mapped[str] = mapped_column(String(40), nullable=False, server_default="hard")
    # hard | five_question | entry_path | advisory

    version: Mapped[StrategyVersion] = relationship(back_populates="rules")


class StrategyScope(Base):
    __tablename__ = "strategy_scopes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_class: Mapped[str] = mapped_column(String(24), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64))
    timeframe: Mapped[str | None] = mapped_column(String(12))
    session: Mapped[str | None] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    version: Mapped[StrategyVersion] = relationship(back_populates="scopes")


class StrategyTestCase(Base):
    __tablename__ = "strategy_test_cases"
    __table_args__ = (
        UniqueConstraint("strategy_version_id", "code", name="uq_strategy_test_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    input_features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    input_context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    expected_setup_state: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_rule_results: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    version: Mapped[StrategyVersion] = relationship(back_populates="test_cases")
