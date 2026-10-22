"""AG-06 Risk agent — policy veto only."""

from __future__ import annotations

from decimal import Decimal

from private_trading_risk.assess import assess_risk
from private_trading_risk.policy import default_policy_config
from private_trading_risk.types import Direction as RiskDirection
from private_trading_risk.types import InstrumentRiskMeta, RiskInput

from private_trading_agents.contracts import (
    AgentId,
    AgentStep,
    RiskAgentIn,
    RiskAgentOut,
)


def run_risk_agent(payload: RiskAgentIn | dict) -> RiskAgentOut:
    inp = RiskAgentIn.model_validate(payload)
    asset_class = inp.asset_class
    risk = assess_risk(
        policy_code=f"default-{asset_class}",
        policy_version_no=1,
        policy_config=default_policy_config(asset_class=asset_class),
        risk_input=RiskInput(
            direction=RiskDirection(inp.direction),
            entry=inp.entry,
            stop=inp.stop,
            target_1=inp.target,
            data_fresh=inp.data_fresh,
            market_actionable=inp.market_actionable,
            account_equity=inp.account_equity,
            instrument=InstrumentRiskMeta(
                asset_class=asset_class,
                price_tick=(
                    Decimal("0.00001")
                    if asset_class == "forex"
                    else Decimal("0.01")
                ),
                qty_step=(
                    Decimal("0.01") if asset_class == "forex" else Decimal("0.001")
                ),
                min_notional=(
                    Decimal("0") if asset_class == "forex" else Decimal("10")
                ),
            ),
        ),
    )
    blockers = list(inp.prior_blockers)
    for blocker in risk.hard_blockers:
        if blocker not in blockers:
            blockers.append(blocker)
    return RiskAgentOut(
        approved=risk.approved,
        entry_price=(
            risk.entry_reference if risk.entry_reference is not None else inp.entry
        ),
        stop_price=risk.stop_price if risk.stop_price is not None else inp.stop,
        target_price=risk.target_1 if risk.target_1 is not None else inp.target,
        rr_ratio=risk.rr_ratio,
        hard_blockers=blockers,
        warnings=list(risk.warnings),
        step=AgentStep(
            agent=AgentId.AG06_RISK,
            status="approved" if risk.approved else "veto",
            note="risk veto",
        ),
    )
