"""AG-05 Strategy agent — versioned rule evaluation only."""

from __future__ import annotations

from decimal import Decimal

from private_trading_strategies.context import DEFAULT_ENTRY_PATH, build_playbook_context
from private_trading_strategies.evaluate import evaluate_strategy
from private_trading_strategies.types import Direction
from private_trading_strategies.wyckoff_hdm import build_wyckoff_hdm_v1

from private_trading_agents.adapters import (
    feature_models_to_payload,
    models_to_candles,
)
from private_trading_agents.contracts import (
    AgentId,
    AgentStatus,
    AgentStep,
    StrategyAgentIn,
    StrategyAgentOut,
)


def run_strategy_agent(payload: StrategyAgentIn | dict) -> StrategyAgentOut:
    inp = StrategyAgentIn.model_validate(payload)
    bars = models_to_candles(inp.bars)
    side = Direction(inp.direction)
    features = feature_models_to_payload(inp.features)
    ctx = build_playbook_context(
        bars,
        inp.bar_index,
        direction=side,
        min_rr=inp.min_rr,
        entry_path=DEFAULT_ENTRY_PATH,
    )
    entry = Decimal(str(ctx["_entry_ref"])) if ctx.get("_entry_ref") else None
    stop = Decimal(str(ctx["_stop_price"])) if ctx.get("_stop_price") else None
    target = None
    if entry is not None and stop is not None:
        risk = abs(entry - stop)
        if risk > 0:
            target = (
                entry + risk * inp.min_rr
                if side == Direction.LONG
                else entry - risk * inp.min_rr
            )
    strategy = build_wyckoff_hdm_v1(
        version_no=1, advisory_definitions=["WYK-001", "IMB-001", "SMT-001"]
    )
    assessment = evaluate_strategy(
        strategy,
        direction=side,
        features=features,
        context={k: v for k, v in ctx.items() if not k.startswith("_")},
    )
    return StrategyAgentOut(
        strategy_code=assessment.strategy_code,
        strategy_version_no=assessment.strategy_version_no,
        setup_state=assessment.setup_state.value,
        direction=side.value,
        blockers=list(assessment.blockers),
        warnings=list(assessment.warnings),
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        step=AgentStep(
            agent=AgentId.AG05_STRATEGY,
            status=AgentStatus.OK.value,
            note=f"setup_state={assessment.setup_state.value}",
        ),
    )
