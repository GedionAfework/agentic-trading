"""AG-05 Strategy agent — versioned rule evaluation only."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStatus,
    AgentStep,
    StrategyAgentIn,
    StrategyAgentOut,
)
from private_trading_agents.tools import ToolId, invoke_tool
from private_trading_agents.tools.schemas import StrategyEvaluateOut


def run_strategy_agent(payload: StrategyAgentIn | dict) -> StrategyAgentOut:
    inp = StrategyAgentIn.model_validate(payload)
    result = invoke_tool(
        agent=AgentId.AG05_STRATEGY,
        tool=ToolId.STRATEGY_EVALUATE,
        payload={
            "direction": inp.direction,
            "features": {
                name: fact.model_dump() for name, fact in inp.features.items()
            },
            "bars": [bar.model_dump() for bar in inp.bars],
            "bar_index": inp.bar_index,
            "min_rr": inp.min_rr,
        },
    )
    assert isinstance(result, StrategyEvaluateOut)
    return StrategyAgentOut(
        strategy_code=result.strategy_code,
        strategy_version_no=result.strategy_version_no,
        setup_state=result.setup_state,
        direction=result.direction,
        blockers=list(result.blockers),
        warnings=list(result.warnings),
        entry_price=result.entry_price,
        stop_price=result.stop_price,
        target_price=result.target_price,
        step=AgentStep(
            agent=AgentId.AG05_STRATEGY,
            status=AgentStatus.OK.value,
            note=f"setup_state={result.setup_state}",
        ),
    )
