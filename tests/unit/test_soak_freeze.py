from private_trading_strategies.multi_market import (
    DOGE_PROFIT_MODEL,
    MarketRegime,
    TradingObjective,
    resolve_market_model,
)
from private_trading_strategies.soak_freeze import (
    SOAK_OBJECTIVE,
    SOAK_SYMBOL,
    SOAK_TIMEFRAME,
    assert_soak_freeze,
    owner_test_symbols,
    soak_incumbent,
    soak_scan_symbols,
    soak_scan_timeframes,
)
from private_trading_strategies.specialist_registry import VALIDATED_SPECIALIST_MODELS


def test_soak_freeze_locks_sol_v1_paper_only() -> None:
    assert_soak_freeze()
    incumbent = soak_incumbent()
    assert SOAK_OBJECTIVE == TradingObjective.PROFIT
    assert soak_scan_symbols() == (SOAK_SYMBOL,)
    assert soak_scan_timeframes() == (SOAK_TIMEFRAME,)
    assert owner_test_symbols() == (
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "DOGE/USDT",
    )
    assert incumbent.code == "sol-mtf-bos-volume-profit"
    assert incumbent.paper_only is True
    assert incumbent.live_alerts_allowed is False
    assert VALIDATED_SPECIALIST_MODELS == ()


def test_owner_set_paper_models_are_sol_and_doge_only() -> None:
    assert (
        resolve_market_model(
            symbol="DOGE/USDT",
            regime=MarketRegime.TREND_HIGH_VOL,
            objective=SOAK_OBJECTIVE,
        )
        is DOGE_PROFIT_MODEL
    )
    for symbol in ("BTC/USDT", "ETH/USDT", "EUR/USD"):
        assert (
            resolve_market_model(
                symbol=symbol,
                regime=MarketRegime.TREND_HIGH_VOL,
                objective=SOAK_OBJECTIVE,
            )
            is None
        )
