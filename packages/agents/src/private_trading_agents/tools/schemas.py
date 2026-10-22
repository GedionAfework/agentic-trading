"""Pydantic I/O for each registered tool."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from private_trading_agents.contracts import CandleBarModel, FeatureFactModel


class FeaturesComputeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bars: list[CandleBarModel] = Field(min_length=1)
    bar_index: int | None = None
    feature_names: list[str] | None = None


class FeaturesComputeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bar_index: int
    bar_open_time: datetime
    features: dict[str, FeatureFactModel]


class StrategyEvaluateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["long", "short"]
    features: dict[str, FeatureFactModel]
    bars: list[CandleBarModel] = Field(min_length=1)
    bar_index: int
    min_rr: Decimal = Decimal("2.0")


class StrategyEvaluateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_code: str
    strategy_version_no: int
    setup_state: str
    direction: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    entry_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None


class RiskAssessIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["long", "short"]
    entry: Decimal | None
    stop: Decimal | None
    target: Decimal | None
    data_fresh: bool
    market_actionable: bool
    asset_class: str = "crypto"
    account_equity: Decimal = Decimal("10000")
    prior_blockers: list[str] = Field(default_factory=list)


class RiskAssessOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    rr_ratio: Decimal | None
    hard_blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExplainGroundedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: dict[str, Any]


class ExplainGroundedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str
    explanation_source: Literal["deterministic"] = "deterministic"


class SignalCheckGatesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setup_state: str
    data_fresh: bool
    market_actionable: bool
    hard_blockers: list[str] = Field(default_factory=list)


class SignalCheckGatesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gates_open_candidate: bool
    hard_blockers: list[str] = Field(default_factory=list)


class VisionCheckVerdictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attached: bool = False
    status: str | None = None
    consistent: bool | None = None
    needs_clarification: bool = False
    blocker: str | None = Field(default=None, max_length=256)


class VisionCheckVerdictOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skipped: bool
    authorizes_trade: Literal[False] = False
    needs_clarification: bool = False
    blocker: str | None = None
    status: str = "skipped"


class MlRankIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    features: dict[str, FeatureFactModel]
    gates_open: bool
    model_mode: str | None = None
    model_present: bool = False


class MlRankOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoked: bool
    model_score: float | None = None
    model_band: str | None = None
    recommends_enter: bool = False
    status: str = "skipped"
    note: str = ""
