"""Pydantic I/O contracts for AG-01..AG-09.

Every agent boundary validates through these models. Untrusted text fields are
plain `str` payloads only — never executable instructions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentId(StrEnum):
    AG01_ORCHESTRATOR = "AG-01"
    AG02_KNOWLEDGE = "AG-02"
    AG03_VISION = "AG-03"
    AG04_MARKET_DATA = "AG-04"
    AG05_STRATEGY = "AG-05"
    AG06_RISK = "AG-06"
    AG07_SIGNAL = "AG-07"
    AG08_JOURNAL = "AG-08"
    AG09_DECISION_ML = "AG-09"


class AgentStatus(StrEnum):
    OK = "ok"
    RUNNING = "running"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    APPROVED = "approved"
    VETO = "veto"
    SCORED = "scored"
    FAILED = "failed"


class AgentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: AgentId
    status: str
    note: str = ""

    def as_workflow_dict(self) -> dict[str, str]:
        return {"agent": self.agent.value, "status": self.status, "note": self.note}


class CandleBarModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    is_final: bool = True


class FeatureFactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    value: Any = None
    reason: str | None = None


class CitationModel(BaseModel):
    """Trusted citation payload from the knowledge corpus (not free-form prompts)."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(min_length=1, max_length=128)
    excerpt: str = Field(default="", max_length=4000)
    document_id: str | None = Field(default=None, max_length=128)


# --- AG-04 Market Data ---


class MarketDataAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=3, max_length=32)
    timeframe: str = Field(min_length=2, max_length=12)
    bars: list[CandleBarModel] = Field(min_length=1)
    data_fresh: bool = True
    market_actionable: bool = True
    bar_index: int | None = None


class MarketDataAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    timeframe: str
    bar_index: int
    bar_open_time: datetime
    data_fresh: bool
    market_actionable: bool
    features: dict[str, FeatureFactModel]
    step: AgentStep


# --- AG-05 Strategy ---


class StrategyAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    timeframe: str
    direction: Literal["long", "short"] = "long"
    features: dict[str, FeatureFactModel]
    bars: list[CandleBarModel]
    bar_index: int
    min_rr: Decimal = Decimal("2.0")
    asset_class: str = "crypto"


class StrategyAgentOut(BaseModel):
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
    step: AgentStep


# --- AG-06 Risk ---


class RiskAgentIn(BaseModel):
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


class RiskAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    entry_price: Decimal | None
    stop_price: Decimal | None
    target_price: Decimal | None
    rr_ratio: Decimal | None
    hard_blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    step: AgentStep


# --- AG-07 Signal ---


class SignalAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setup_state: str
    data_fresh: bool
    market_actionable: bool
    hard_blockers: list[str] = Field(default_factory=list)


class SignalAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gates_open_candidate: bool
    hard_blockers: list[str] = Field(default_factory=list)
    step: AgentStep


# --- AG-09 Decision ML ---


class DecisionMlAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    features: dict[str, FeatureFactModel]
    gates_open: bool
    model_mode: str | None = None
    model_present: bool = False


class DecisionMlAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoked: bool
    model_score: float | None = None
    model_band: str | None = None
    recommends_enter: bool = False
    step: AgentStep


# --- AG-03 Vision ---


class VisionAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Opaque supporting evidence only. Never authorizes trades.
    status: str | None = None
    consistent: bool | None = None
    needs_clarification: bool = False
    blocker: str | None = Field(default=None, max_length=256)
    attached: bool = False


class VisionAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorizes_trade: Literal[False] = False
    needs_clarification: bool = False
    blocker: str | None = None
    step: AgentStep


# --- AG-02 Knowledge / explanation ---


class KnowledgeAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: dict[str, Any]
    citations: list[CitationModel] = Field(default_factory=list)


class KnowledgeAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str
    explanation_source: str
    step: AgentStep


# --- AG-08 Journal (stub contract; narrative comes later) ---


class JournalAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False


class JournalAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: AgentStep


# --- AG-01 Orchestrator ---


class OrchestratorAgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=3, max_length=32)
    timeframe: str = Field(min_length=2, max_length=12)
    bars: list[CandleBarModel] = Field(min_length=1)
    bar_index: int | None = None
    direction: Literal["long", "short"] = "long"
    data_fresh: bool = True
    market_actionable: bool = True
    position_state: Literal["flat", "open"] = "flat"
    citations: list[CitationModel] = Field(default_factory=list)
    min_rr: str = "2.0"
    asset_class: str = "crypto"
    model_id: UUID | None = None
    model_mode: str | None = None
    model_present: bool = False
    vision: VisionAgentIn | None = None


class DecisionActionName(StrEnum):
    ENTER = "ENTER"
    WAIT = "WAIT"
    HOLD = "HOLD"
    EXIT = "EXIT"
    NO_SETUP = "NO_SETUP"


class OrchestratorAgentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    timeframe: str
    bar_open_time: datetime
    action: DecisionActionName
    direction: str
    setup_state: str
    confidence_band: str
    strategy_code: str
    strategy_version_no: int
    risk_approved: bool
    entry_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    rr_ratio: Decimal | None = None
    model_id: UUID | None = None
    model_score: float | None = None
    model_band: str | None = None
    explanation: str
    explanation_source: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    workflow: list[dict[str, str]] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    step: AgentStep
