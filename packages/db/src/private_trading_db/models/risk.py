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


class RiskPolicy(Base):
    __tablename__ = "risk_policies"

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

    versions: Mapped[list[RiskPolicyVersion]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )


class RiskPolicyVersion(Base):
    __tablename__ = "risk_policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version_no", name="uq_risk_policy_version_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    # Engineering-candidate defaults until D-01 locks — stored explicitly in JSON.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    policy: Mapped[RiskPolicy] = relationship(back_populates="versions")
    assessments: Mapped[list[RiskAssessment]] = relationship(back_populates="policy_version")


class RiskAssessment(Base):
    """Persisted risk result. setup_id is a logical ref until setups table lands."""

    __tablename__ = "risk_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_policy_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    setup_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_reference: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    target_1: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    risk_distance: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    reward_distance: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    rr_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    hard_blockers: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    paper_size: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    policy_version: Mapped[RiskPolicyVersion] = relationship(back_populates="assessments")
