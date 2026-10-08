from private_trading_strategies.challenger import (
    SOL_MTF_CHALLENGER_V1,
    SOL_MTF_CHALLENGER_V2_SCALE_OUT,
)


def test_sol_challenger_is_narrow_and_paper_only() -> None:
    spec = SOL_MTF_CHALLENGER_V1
    assert spec.symbol == "SOL/USDT"
    assert spec.direction == "long"
    assert spec.higher_timeframe == "4h"
    assert spec.entry_timeframe == "1h"
    assert spec.ema_periods == (12, 21, 50)
    assert spec.volume_ratio_min == 2.0
    assert spec.target_r == 3.0
    assert spec.paper_only is True
    assert spec.live_alerts_allowed is False


def test_sol_scale_out_challenger_takes_partial_profit_and_remains_paper_only() -> None:
    spec = SOL_MTF_CHALLENGER_V2_SCALE_OUT
    assert spec.symbol == "SOL/USDT"
    assert spec.target_r == 4.0
    assert spec.partial_profit_at_r == 1.25
    assert spec.partial_profit_fraction == 0.5
    assert spec.move_stop_to_breakeven_after_partial is True
    assert spec.paper_only is True
    assert spec.live_alerts_allowed is False
