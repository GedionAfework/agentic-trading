"""Step 0 paper-soak freeze.

Incumbent model codes and the soak profile are locked here. Do not retune
V1/V2 against 2022–2026. A later research version must beat these codes on
unused bars before it can replace them.
"""

from __future__ import annotations

from private_trading_strategies.challenger import (
    SOL_MTF_CHALLENGER_V1,
    SOL_MTF_CHALLENGER_V2_SCALE_OUT,
)
from private_trading_strategies.multi_market import (
    PAPER_MODEL_REGISTRY,
    SOL_PROFIT_MODEL,
    SOL_WIN_RATE_MODEL,
    MarketModelSpec,
    TradingObjective,
)
from private_trading_strategies.specialist_registry import VALIDATED_SPECIALIST_MODELS

SOAK_FREEZE_ID = "soak-v1-2026-10-08"
SOAK_SYMBOL = "SOL/USDT"
SOAK_TIMEFRAME = "1h"
SOAK_HIGHER_TIMEFRAME = "4h"
SOAK_OBJECTIVE = TradingObjective.PROFIT
SOAK_PROFILE_REASON = (
    "V1 has the strongest after-cost walk-forward expectancy (+0.215R). "
    "V2 stays frozen as the win-rate alternate and is not the active soak."
)
# Last committed SHA when this freeze was written. Working-tree model codes
# are the lock; do not treat a dirty tree as a new research version.
SOAK_GIT_SHA = "937a58117ddbd80abee54d12d006f11fda49e0ac"
SELECTION_DATA_THROUGH = "2025-12-31"
SOAK_STEP1_MIN_CLOSED_TRADES = 20
SOAK_STEP2_MIN_CLOSED_TRADES = 80
SOAK_STEP2_MIN_MEAN_R = 0.0
SOAK_STEP2_MIN_PROFIT_FACTOR = 1.1
SOAK_STEP2_MAX_DRAWDOWN_R = 20.0
SOAK_STEP2_MIN_POSITIVE_MONTH_FRACTION = 0.6
SOAK_STEP2_MIN_TRADES_PER_MONTH = 4
SOAK_STEP2_MAX_EXTRA_COST_BPS = 2.0
SOAK_RESEARCH_MEAN_R = 0.215
SOAK_RESEARCH_WIN_RATE = 0.409
# Paper trades on/after this date are the only unused holdout for active V1 soak.
# Calendar 2022–2026 was already used in walk-forward selection/test folds.
SOAK_HOLDOUT_START = "2026-10-08"
SOAK_HOLDOUT_MIN_MEAN_R_FRACTION_OF_RESEARCH = 0.5

SOAK_FILL_MODEL = {
    "label": "PAPER",
    "fill_policy": "next_open",
    "same_candle_ambiguity": "conservative_stop_first",
    "fee_bps": "10",
    "slippage_bps": "5",
    "spread_bps": "2",
    "max_bars_in_trade": 80,
    "risk_pct": "0.5",
    "research_pair_fill_bps": "8",
    "notes": [
        "Paper fee 10 bps per side matches the 0.001 crypto taker used in research.",
        "Slippage 5 + spread 2 is the paper engine default; research used 8 bps "
        "combined fill degradation for SOL. Log the gap; do not retune entries.",
    ],
}


def soak_incumbent() -> MarketModelSpec:
    if SOAK_OBJECTIVE == TradingObjective.PROFIT:
        return SOL_PROFIT_MODEL
    return SOL_WIN_RATE_MODEL


def soak_scan_symbols() -> tuple[str, ...]:
    return (SOAK_SYMBOL,)


def soak_scan_timeframes() -> tuple[str, ...]:
    return (SOAK_TIMEFRAME,)


def owner_test_symbols() -> tuple[str, ...]:
    """Owner 2-week coin set. Paper opens still require a validated model."""
    from private_trading_market_data.universe import OWNER_CRYPTO_SYMBOLS

    return OWNER_CRYPTO_SYMBOLS


def assert_soak_freeze() -> None:
    """Fail closed if a specialist or live-alert model leaked into the soak."""
    if VALIDATED_SPECIALIST_MODELS:
        raise AssertionError("specialist registry must stay empty during soak freeze")
    from private_trading_strategies.multi_market import DOGE_PROFIT_MODEL

    expected = (SOL_PROFIT_MODEL, SOL_WIN_RATE_MODEL, DOGE_PROFIT_MODEL)
    if expected != PAPER_MODEL_REGISTRY:
        raise AssertionError("paper registry freeze drifted from SOL V1/V2 + DOGE V1")
    for spec in (SOL_MTF_CHALLENGER_V1, SOL_MTF_CHALLENGER_V2_SCALE_OUT):
        if spec.symbol != SOAK_SYMBOL:
            raise AssertionError(f"{spec.code} is not the soak symbol")
        if not spec.paper_only or spec.live_alerts_allowed:
            raise AssertionError(f"{spec.code} is not paper-only")
    for spec in PAPER_MODEL_REGISTRY:
        if not spec.paper_only or spec.live_alerts_allowed:
            raise AssertionError(f"{spec.code} is not paper-only")
        if not spec.validated_for_paper:
            raise AssertionError(f"{spec.code} missing paper validation")
    incumbent = soak_incumbent()
    if not incumbent.validated_for_paper or incumbent.live_alerts_allowed:
        raise AssertionError("soak incumbent cannot authorize live alerts")
    if incumbent.entry_timeframe != SOAK_TIMEFRAME:
        raise AssertionError("soak timeframe freeze drifted")
