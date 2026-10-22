from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_features.specialist import (
    beta_adjusted_return,
    forex_session,
    in_liquid_forex_session,
    relative_strength,
)
from private_trading_features.types import CandleBar
from private_trading_strategies.multi_market import MarketRegime
from private_trading_strategies.specialist_catalog import specialist_candidates
from private_trading_strategies.specialists import (
    TREND_REGIMES,
    SpecialistAction,
    SpecialistConfig,
    SpecialistContext,
    StrategyFamily,
    evaluate_specialist,
)


def _bars(
    count: int,
    *,
    step: str = "0.1",
    start_hour: int = 0,
    breakout: bool = False,
) -> list[CandleBar]:
    start = datetime(2025, 1, 1, start_hour, tzinfo=UTC)
    rows: list[CandleBar] = []
    for index in range(count):
        close = Decimal("100") + Decimal(index) * Decimal(step)
        if breakout and index == count - 1:
            close += Decimal("5")
        rows.append(
            CandleBar(
                open_time=start + timedelta(hours=index),
                open=close - Decimal("0.2"),
                high=close + Decimal("0.4"),
                low=close - Decimal("0.4"),
                close=close,
                volume=Decimal("200") if index == count - 1 else Decimal("100"),
                is_final=True,
            )
        )
    return rows


def test_btc_trend_breakout_specialist_enters_on_completed_breakout() -> None:
    config = SpecialistConfig(
        code="btc-breakout-test",
        family=StrategyFamily.TREND_BREAKOUT,
        symbol="BTC/USDT",
        asset_class="crypto",
        allowed_regimes=TREND_REGIMES,
        rr=Decimal("2"),
        max_bars=40,
        volume_ratio_min=Decimal("1.5"),
    )
    signal = evaluate_specialist(
        config,
        SpecialistContext(
            entry_bars=_bars(80, breakout=True),
            higher_timeframe_bars=_bars(70),
            regime=MarketRegime.TREND_HIGH_VOL,
        ),
    )
    assert signal.action == SpecialistAction.ENTER
    assert signal.direction == "long"
    assert signal.stop_price is not None
    assert signal.target_price is not None


def test_symbol_cannot_use_an_unassigned_family() -> None:
    config = SpecialistConfig(
        code="btc-range-test",
        family=StrategyFamily.RANGE_REVERSION,
        symbol="BTC/USDT",
        asset_class="crypto",
        allowed_regimes=(MarketRegime.RANGE_HIGH_VOL,),
        rr=Decimal("1"),
        max_bars=20,
    )
    signal = evaluate_specialist(
        config,
        SpecialistContext(
            entry_bars=_bars(80),
            higher_timeframe_bars=_bars(70),
            regime=MarketRegime.RANGE_HIGH_VOL,
        ),
    )
    assert signal.action == SpecialistAction.WAIT
    assert signal.reason == "family_not_allowed_for_symbol"


def test_relative_strength_and_forex_sessions_are_deterministic() -> None:
    strong = _bars(30, step="0.3")
    benchmark = _bars(30, step="0.1")
    strength = relative_strength(strong, benchmark, 29, 20)
    adjusted = beta_adjusted_return(strong, benchmark, 29, 20)
    assert strength is not None and strength > 0
    assert adjusted is not None
    assert forex_session(8) == "london"
    assert forex_session(14) == "overlap"
    assert forex_session(18) == "new_york_late"
    assert forex_session(23) == "asia"
    assert in_liquid_forex_session(8)
    assert in_liquid_forex_session(18)
    assert not in_liquid_forex_session(23)


def test_each_pair_has_a_bounded_asset_specific_candidate_catalog() -> None:
    btc = specialist_candidates("BTC/USDT")
    eth = specialist_candidates("ETH/USDT")
    bnb = specialist_candidates("BNB/USDT")
    eur = specialist_candidates("EUR/USD")
    gbp = specialist_candidates("GBP/USD")
    assert {item.family for item in btc} != {item.family for item in eth}
    assert any(item.family == StrategyFamily.RELATIVE_STRENGTH for item in eth)
    assert any(item.use_beta_adjustment for item in eth)
    assert any(item.family == StrategyFamily.RANGE_REVERSION for item in bnb)
    assert any(item.family == StrategyFamily.PULLBACK_CONTINUATION for item in bnb)
    assert {item.family for item in eur} == {item.family for item in gbp}
    assert StrategyFamily.SESSION_BREAKOUT in {item.family for item in eur}
    assert StrategyFamily.SESSION_PULLBACK in {item.family for item in eur}
    assert StrategyFamily.RANGE_REVERSION in {item.family for item in eur}
    assert all(item.volume_ratio_min is not None for item in btc)
    assert all(item.volume_ratio_min is None for item in eur)
    assert 1 <= len(btc) <= 8
    assert 1 <= len(eur) <= 8


def test_eth_relative_strength_waits_without_benchmark() -> None:
    config = SpecialistConfig(
        code="eth-rs-test",
        family=StrategyFamily.RELATIVE_STRENGTH,
        symbol="ETH/USDT",
        asset_class="crypto",
        allowed_regimes=TREND_REGIMES,
        rr=Decimal("2"),
        max_bars=40,
        volume_ratio_min=Decimal("1.5"),
    )
    signal = evaluate_specialist(
        config,
        SpecialistContext(
            entry_bars=_bars(80, breakout=True),
            higher_timeframe_bars=_bars(70),
            regime=MarketRegime.TREND_HIGH_VOL,
        ),
    )
    assert signal.action == SpecialistAction.WAIT
    assert signal.reason == "benchmark_missing"


def test_bnb_range_reversion_buys_stretched_oversold_close() -> None:
    config = SpecialistConfig(
        code="bnb-range-test",
        family=StrategyFamily.RANGE_REVERSION,
        symbol="BNB/USDT",
        asset_class="crypto",
        allowed_regimes=(MarketRegime.RANGE_LOW_VOL,),
        rr=Decimal("1"),
        max_bars=20,
        range_entry_atr=Decimal("0.1"),
    )
    bars = _bars(80, step="0")
    last = bars[-1]
    bars[-1] = CandleBar(
        open_time=last.open_time,
        open=Decimal("97.6"),
        high=Decimal("98.1"),
        low=Decimal("97.4"),
        close=Decimal("98.0"),
        volume=Decimal("100"),
        is_final=True,
    )
    signal = evaluate_specialist(
        config,
        SpecialistContext(
            entry_bars=bars,
            higher_timeframe_bars=_bars(70, step="0.001"),
            regime=MarketRegime.RANGE_LOW_VOL,
        ),
    )
    assert signal.action == SpecialistAction.ENTER
    assert signal.direction == "long"


def test_forex_session_specialist_enters_during_london_breakout() -> None:
    config = SpecialistConfig(
        code="eur-session-enter-test",
        family=StrategyFamily.SESSION_BREAKOUT,
        symbol="EUR/USD",
        asset_class="forex",
        allowed_regimes=TREND_REGIMES,
        rr=Decimal("2"),
        max_bars=40,
    )
    signal = evaluate_specialist(
        config,
        SpecialistContext(
            entry_bars=_bars(80, start_hour=8, breakout=True),
            higher_timeframe_bars=_bars(70),
            regime=MarketRegime.TREND_HIGH_VOL,
        ),
    )
    assert signal.action == SpecialistAction.ENTER
    assert signal.direction == "long"


def test_forex_session_specialist_waits_outside_london_hours() -> None:
    config = SpecialistConfig(
        code="eur-session-test",
        family=StrategyFamily.SESSION_BREAKOUT,
        symbol="EUR/USD",
        asset_class="forex",
        allowed_regimes=TREND_REGIMES,
        rr=Decimal("2"),
        max_bars=40,
    )
    signal = evaluate_specialist(
        config,
        SpecialistContext(
            entry_bars=_bars(80, start_hour=23, breakout=True),
            higher_timeframe_bars=_bars(70),
            regime=MarketRegime.TREND_HIGH_VOL,
        ),
    )
    assert signal.action == SpecialistAction.WAIT
    assert signal.reason == "outside_liquid_forex_session"


def test_sol_volatility_expansion_waits_without_contraction() -> None:
    config = SpecialistConfig(
        code="sol-vol-test",
        family=StrategyFamily.VOLATILITY_EXPANSION,
        symbol="SOL/USDT",
        asset_class="crypto",
        allowed_regimes=TREND_REGIMES,
        rr=Decimal("3"),
        max_bars=80,
        volume_ratio_min=Decimal("1.5"),
    )
    signal = evaluate_specialist(
        config,
        SpecialistContext(
            entry_bars=_bars(80, breakout=True),
            higher_timeframe_bars=_bars(70),
            regime=MarketRegime.TREND_HIGH_VOL,
        ),
    )
    assert signal.action == SpecialistAction.WAIT
    assert signal.reason == "no_contraction_expansion"
