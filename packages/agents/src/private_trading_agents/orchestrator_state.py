"""Mutable AG-01 state shared across routing tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from private_trading_decision.predict import LoadedModel
from private_trading_features.types import CandleBar
from private_trading_strategies.types import SetupState

from private_trading_agents.adapters import candles_to_models, feature_models_to_payload
from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    CitationModel,
    DecisionActionName,
    DecisionMlAgentOut,
    JournalAgentOut,
    KnowledgeAgentOut,
    MarketDataAgentOut,
    RiskAgentOut,
    SignalAgentOut,
    StrategyAgentOut,
    VisionAgentIn,
    VisionAgentOut,
)
from private_trading_agents.tools.policy import PolicyGraph


@dataclass(slots=True)
class OrchestratorState:
    bars: list[CandleBar]
    symbol: str
    timeframe: str
    bar_index: int | None
    direction: str
    data_fresh: bool
    market_actionable: bool
    position_state: Literal["flat", "open"]
    citations: list[CitationModel]
    min_rr: str
    asset_class: str
    model: LoadedModel | None
    model_id: UUID | None
    model_mode: str | None
    vision_in: VisionAgentIn | None
    policy: PolicyGraph = field(default_factory=PolicyGraph)
    workflow: list[dict[str, str]] = field(default_factory=list)
    market: MarketDataAgentOut | None = None
    vision_out: VisionAgentOut | None = None
    journal_out: JournalAgentOut | None = None
    strategy: StrategyAgentOut | None = None
    signal: SignalAgentOut | None = None
    risk: RiskAgentOut | None = None
    ml: DecisionMlAgentOut | None = None
    knowledge: KnowledgeAgentOut | None = None
    action: Any | None = None
    hard_blockers: list[str] = field(default_factory=list)
    finished: bool = False
    snapshot: Any | None = None

    def candle_models(self) -> list:
        return candles_to_models(self.bars)

    def ensure_workflow_head(self) -> None:
        if not self.workflow:
            self.workflow.append(
                AgentStep(
                    agent=AgentId.AG01_ORCHESTRATOR,
                    status="running",
                    note="agentic orchestrator",
                ).as_workflow_dict()
            )

    def resolve_action(self) -> Any:
        from private_trading_agents.workflow import DecisionAction

        if self.action is not None:
            return self.action
        if self.market is None or self.strategy is None or self.signal is None or self.risk is None:
            raise RuntimeError("cannot resolve action before required specialists run")
        hard_blockers = list(self.risk.hard_blockers)
        gates_open = self.signal.gates_open_candidate and self.risk.approved
        model_says_enter = bool(self.ml.recommends_enter) if self.ml else False

        if self.position_state == "open":
            action = DecisionAction.HOLD if gates_open else DecisionAction.EXIT
        elif (
            self.strategy.setup_state == SetupState.NO_SETUP.value
            and self.market.data_fresh
            and self.market.market_actionable
        ):
            action = DecisionAction.NO_SETUP
        elif not gates_open:
            action = DecisionAction.WAIT
        elif (
            self.model is not None
            and (self.model_mode or "shadow") == "champion"
            and not model_says_enter
        ):
            action = DecisionAction.WAIT
            hard_blockers.append("model_abstain")
        else:
            action = DecisionAction.ENTER

        vision_out = self.vision_out
        if vision_out and vision_out.needs_clarification and action == DecisionAction.ENTER:
            action = DecisionAction.WAIT
            if vision_out.blocker and vision_out.blocker not in hard_blockers:
                hard_blockers.append(vision_out.blocker)

        self.action = action
        self.hard_blockers = hard_blockers
        return action

    def build_snapshot(self) -> Any:
        from private_trading_agents.workflow import DecisionSnapshot, _confidence

        if self.market is None or self.strategy is None or self.risk is None:
            raise RuntimeError("cannot finish without market/strategy/risk")
        action = self.resolve_action()
        model_score = self.ml.model_score if self.ml else None
        model_band = self.ml.model_band if self.ml else None
        band = _confidence(
            action=action,
            risk_approved=self.risk.approved,
            model_band=model_band,
            model_mode=self.model_mode,
        )
        features = feature_models_to_payload(self.market.features)
        citation_rows = [item.model_dump() for item in self.citations]
        explanation = (
            self.knowledge.explanation
            if self.knowledge is not None
            else f"Action {action.value} on {self.symbol} {self.timeframe}."
        )
        explanation_source = (
            self.knowledge.explanation_source if self.knowledge is not None else "deterministic"
        )
        DecisionActionName(action.value)
        self.workflow[0] = AgentStep(
            agent=AgentId.AG01_ORCHESTRATOR,
            status="ok",
            note=f"action={action.value}",
        ).as_workflow_dict()
        snapshot = DecisionSnapshot(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bar_open_time=self.market.bar_open_time,
            action=action,
            direction=self.strategy.direction,
            setup_state=self.strategy.setup_state,
            confidence_band=band,
            strategy_code=self.strategy.strategy_code,
            strategy_version_no=self.strategy.strategy_version_no,
            risk_approved=self.risk.approved,
            entry_price=self.risk.entry_price,
            stop_price=self.risk.stop_price,
            target_price=self.risk.target_price,
            rr_ratio=self.risk.rr_ratio,
            model_id=self.model_id,
            model_score=model_score,
            model_band=model_band,
            explanation=explanation,
            explanation_source=explanation_source,
            evidence={
                "features": features,
                "strategy_blockers": list(self.strategy.blockers),
                "risk_blockers": list(self.risk.hard_blockers),
                "citations": citation_rows,
                "position_state": self.position_state,
                "workflow_version": "0.2.0",
                "contracts": "pydantic_v1",
                "orchestrator_mode": "agentic",
                "policy_completed": sorted(t.value for t in self.policy.completed),
            },
            workflow=list(self.workflow),
            hard_blockers=list(self.hard_blockers),
        )
        self.snapshot = snapshot
        self.finished = True
        return snapshot

    def knowledge_facts(self) -> dict[str, Any]:
        from private_trading_agents.workflow import _confidence

        action = self.resolve_action()
        assert self.market is not None and self.strategy is not None and self.risk is not None
        model_score = self.ml.model_score if self.ml else None
        model_band = self.ml.model_band if self.ml else None
        band = _confidence(
            action=action,
            risk_approved=self.risk.approved,
            model_band=model_band,
            model_mode=self.model_mode,
        )
        return {
            "action": action.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bar_open_time": self.market.bar_open_time.isoformat(),
            "strategy_code": self.strategy.strategy_code,
            "strategy_version_no": self.strategy.strategy_version_no,
            "setup_state": self.strategy.setup_state,
            "hard_blockers": list(self.hard_blockers),
            "risk_approved": self.risk.approved,
            "entry_price": self.risk.entry_price,
            "stop_price": self.risk.stop_price,
            "target_price": self.risk.target_price,
            "rr_ratio": self.risk.rr_ratio,
            "features": feature_models_to_payload(self.market.features),
            "citations": [item.model_dump() for item in self.citations],
            "model_score": model_score,
            "model_band": model_band,
            "model_invoked": self.model is not None,
            "confidence_band": band,
            "extra_numbers": [self.min_rr],
        }
