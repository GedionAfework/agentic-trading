"""AG-04 Market Data agent — normalized bars + feature facts only."""

from __future__ import annotations

from private_trading_decision.labels import FEATURE_NAMES
from private_trading_features.engine import compute_feature

from private_trading_agents.adapters import (
    feature_payload_to_models,
    models_to_candles,
)
from private_trading_agents.contracts import (
    AgentId,
    AgentStatus,
    AgentStep,
    FeatureFactModel,
    MarketDataAgentIn,
    MarketDataAgentOut,
)


def run_market_data_agent(payload: MarketDataAgentIn | dict) -> MarketDataAgentOut:
    inp = MarketDataAgentIn.model_validate(payload)
    bars = models_to_candles(inp.bars)
    index = len(bars) - 1 if inp.bar_index is None else inp.bar_index
    if index < 0 or index >= len(bars):
        raise ValueError("bar_index out of range")
    features: dict[str, FeatureFactModel] = {}
    raw: dict = {}
    for name in FEATURE_NAMES:
        value = compute_feature(name, bars, index)
        numeric = value.value
        if hasattr(numeric, "__float__") and numeric is not None:
            try:
                from decimal import Decimal

                if isinstance(numeric, Decimal):
                    numeric = float(numeric)
            except Exception:  # noqa: BLE001
                pass
        raw[name] = {
            "status": value.status.value,
            "value": numeric,
            "reason": value.reason,
        }
    features = feature_payload_to_models(raw)
    return MarketDataAgentOut(
        symbol=inp.symbol,
        timeframe=inp.timeframe,
        bar_index=index,
        bar_open_time=bars[index].open_time,
        data_fresh=inp.data_fresh,
        market_actionable=inp.market_actionable,
        features=features,
        step=AgentStep(
            agent=AgentId.AG04_MARKET_DATA,
            status=AgentStatus.OK.value,
            note=(
                f"{inp.symbol} {inp.timeframe} bar {index} "
                f"fresh={inp.data_fresh}"
            ),
        ),
    )
