"""AG-06 Risk agent — policy veto only."""

from __future__ import annotations

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    RiskAgentIn,
    RiskAgentOut,
)
from private_trading_agents.tools import ToolId, invoke_tool
from private_trading_agents.tools.schemas import RiskAssessOut


def run_risk_agent(payload: RiskAgentIn | dict) -> RiskAgentOut:
    inp = RiskAgentIn.model_validate(payload)
    result = invoke_tool(
        agent=AgentId.AG06_RISK,
        tool=ToolId.RISK_ASSESS,
        payload={
            "direction": inp.direction,
            "entry": inp.entry,
            "stop": inp.stop,
            "target": inp.target,
            "data_fresh": inp.data_fresh,
            "market_actionable": inp.market_actionable,
            "asset_class": inp.asset_class,
            "account_equity": inp.account_equity,
            "prior_blockers": list(inp.prior_blockers),
        },
    )
    assert isinstance(result, RiskAssessOut)
    return RiskAgentOut(
        approved=result.approved,
        entry_price=result.entry_price,
        stop_price=result.stop_price,
        target_price=result.target_price,
        rr_ratio=result.rr_ratio,
        hard_blockers=list(result.hard_blockers),
        warnings=list(result.warnings),
        step=AgentStep(
            agent=AgentId.AG06_RISK,
            status="approved" if result.approved else "veto",
            note="risk veto",
        ),
    )
