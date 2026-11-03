import math
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from private_trading_features.types import CandleBar
from private_trading_paper_trade.btc_shadow import MIN_TRADES_PER_BUCKET, split_by_btc_regime
from private_trading_strategies.btc_regime import BTC_REGIME_RULE, classify_btc_regime

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(closes: list[float], *, final: bool = True) -> list[CandleBar]:
    return [
        CandleBar(
            open_time=T0 + timedelta(hours=4 * i),
            open=Decimal(str(c)),
            high=Decimal(str(c * 1.01)),
            low=Decimal(str(c * 0.99)),
            close=Decimal(str(c)),
            volume=Decimal("1"),
            is_final=final,
        )
        for i, c in enumerate(closes)
    ]


def test_uptrend_is_risk_on() -> None:
    tag = classify_btc_regime(_bars([100 + i for i in range(120)]))
    assert tag.risk_on is True
    assert tag.as_dict()["label"] == "risk_on"
    assert tag.as_dict()["shadow_only"] is True
    assert tag.rule == BTC_REGIME_RULE


def test_downtrend_and_chop_are_risk_off() -> None:
    assert classify_btc_regime(_bars([300 - i for i in range(120)])).risk_on is False
    # Uptrend, then a break below the averages: stack fails -> risk-off.
    broken = [100 + i for i in range(110)] + [150, 145, 140, 135, 130]
    assert classify_btc_regime(_bars(broken)).risk_on is False


def test_short_history_is_unknown_not_risk_off() -> None:
    tag = classify_btc_regime(_bars([100 + i for i in range(40)]))
    assert tag.risk_on is None
    assert tag.as_dict()["label"] == "unknown"


def test_open_candle_is_ignored() -> None:
    closed = _bars([100 + i for i in range(120)])
    # A crashing, still-open candle must not flip the tag.
    live = _bars([1.0], final=False)[0]
    live = CandleBar(
        open_time=closed[-1].open_time + timedelta(hours=4),
        open=live.open, high=live.high, low=live.low, close=live.close,
        volume=live.volume, is_final=False,
    )
    assert classify_btc_regime([*closed, live]).risk_on is True


def test_matches_research_rule_bar_for_bar() -> None:
    """Production tag == scripts/_mtf_oos_search.htf_passes(stack_slope)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from _mtf_oos_search import MtfSeries, htf_passes
    from _oos_strategy_search import Series, ema

    closes = [100 + 10 * math.sin(i / 9) + i * 0.15 for i in range(260)]
    stub = Series(symbol="BTC/USDT", times=[], opens=[], highs=[], lows=[], closes=[],
                  volumes=[], ema12=[], ema21=[], ema50=[], swing_high=[], swing_low=[],
                  vol_ratio=[])
    series = MtfSeries(
        entry=stub,
        htf_index=list(range(len(closes))),
        htf_closes=closes,
        htf_ema12=ema(closes, 12),
        htf_ema21=ema(closes, 21),
        htf_ema50=ema(closes, 50),
    )
    bars = _bars(closes)
    checked = 0
    for j in range(60, len(closes)):
        assert classify_btc_regime(bars[: j + 1]).risk_on == htf_passes(series, j, "stack_slope")
        checked += 1
    assert checked > 100


def test_split_needs_enough_trades_per_bucket() -> None:
    rows = [("sol-v1", "risk_on", 3.0), ("sol-v1", "risk_off", -1.0), ("sol-v1", "unknown", 1.0)]
    report = split_by_btc_regime(rows)
    model = report["models"][0]
    assert model["risk_on"]["win_rate"] == 1.0
    assert model["risk_off"]["mean_r"] == -1.0
    assert model["unknown"]["trades"] == 1
    assert model["enough_sample"] is False
    assert "insufficient" in model["verdict"]
    assert report["shadow_only"] is True


def test_split_compares_once_both_buckets_are_large() -> None:
    n = MIN_TRADES_PER_BUCKET
    rows = [("doge-v1", "risk_on", 1.0)] * n + [("doge-v1", "risk_off", -0.5)] * n
    model = split_by_btc_regime(rows)["models"][0]
    assert model["enough_sample"] is True and model["verdict"] == "compare"
