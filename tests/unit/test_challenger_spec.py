from private_trading_strategies.challenger import SOL_MTF_CHALLENGER_V1


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
