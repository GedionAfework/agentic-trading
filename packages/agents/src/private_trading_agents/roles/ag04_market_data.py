"""AG-04 Market Data agent — normalized bars + feature facts only."""

from __future__ import annotations

from private_trading_agents.agent_runtime import call_tool
from private_trading_agents.contracts import (
    AgentId,
    AgentStatus,
    AgentStep,
    MarketDataAgentIn,
    MarketDataAgentOut,
)
from private_trading_agents.tools import ToolId
from private_trading_agents.tools.schemas import FeaturesComputeOut


def run_market_data_agent(payload: MarketDataAgentIn | dict) -> MarketDataAgentOut:
    inp = MarketDataAgentIn.model_validate(payload)
    result = call_tool(
        agent=AgentId.AG04_MARKET_DATA,
        tool=ToolId.FEATURES_COMPUTE,
        payload={
            "bars": [bar.model_dump() for bar in inp.bars],
            "bar_index": inp.bar_index,
        },
        note="compute features",
    )
    assert isinstance(result, FeaturesComputeOut)
    return MarketDataAgentOut(
        symbol=inp.symbol,
        timeframe=inp.timeframe,
        bar_index=result.bar_index,
        bar_open_time=result.bar_open_time,
        data_fresh=inp.data_fresh,
        market_actionable=inp.market_actionable,
        features=result.features,
        step=AgentStep(
            agent=AgentId.AG04_MARKET_DATA,
            status=AgentStatus.OK.value,
            note=(
                f"{inp.symbol} {inp.timeframe} bar {result.bar_index} "
                f"fresh={inp.data_fresh}"
            ),
        ),
    )
