from private_trading_backtest.walkforward import (
    ResearchPerformance,
    evaluate_promotion,
)
from private_trading_strategies.challenger import (
    SOL_MTF_CHALLENGER_V1,
    SOL_MTF_CHALLENGER_V3_DAILY4H,
    STEP6_CATALOG_VERSION,
    V1_INCUMBENT_MEAN_R,
)
from private_trading_strategies.multi_market import PAPER_MODEL_REGISTRY
from private_trading_strategies.specialist_registry import VALIDATED_SPECIALIST_MODELS


def test_step6_v3_uses_unused_timeframe_stack() -> None:
    assert SOL_MTF_CHALLENGER_V3_DAILY4H.higher_timeframe == "1d"
    assert SOL_MTF_CHALLENGER_V3_DAILY4H.entry_timeframe == "4h"
    assert SOL_MTF_CHALLENGER_V1.higher_timeframe == "4h"
    assert SOL_MTF_CHALLENGER_V1.entry_timeframe == "1h"
    assert SOL_MTF_CHALLENGER_V3_DAILY4H.paper_only is True
    assert SOL_MTF_CHALLENGER_V3_DAILY4H.live_alerts_allowed is False
    assert STEP6_CATALOG_VERSION.startswith("sol-mtf-daily4h")


def test_step6_v3_not_in_paper_or_specialist_registry() -> None:
    codes = {model.code for model in PAPER_MODEL_REGISTRY}
    assert SOL_MTF_CHALLENGER_V3_DAILY4H.code not in codes
    assert VALIDATED_SPECIALIST_MODELS == ()


def test_step6_promotion_must_beat_v1_expectancy() -> None:
    almost = ResearchPerformance([0.20] * 100)
    decision = evaluate_promotion(
        [almost],
        min_total_trades=80,
        min_mean_r=0.05,
        min_profit_factor=1.1,
        max_drawdown_r=20.0,
        min_positive_period_fraction=0.6,
        incumbent_mean_r=V1_INCUMBENT_MEAN_R,
    )
    assert decision.approved is False
    assert "did_not_beat_incumbent_expectancy" in decision.reasons
