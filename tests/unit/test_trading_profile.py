"""Client trading-profile choice: V1 expectancy vs V2 win-rate."""

from __future__ import annotations

from private_trading_strategies.multi_market import (
    SOL_PROFIT_MODEL,
    SOL_WIN_RATE_MODEL,
    TradingObjective,
)
from private_trading_strategies.trading_profile import (
    DEFAULT_TRADING_OBJECTIVE,
    list_trading_profiles,
    model_for_objective,
    parse_trading_objective,
)


def test_default_is_profit_v1() -> None:
    assert DEFAULT_TRADING_OBJECTIVE == TradingObjective.PROFIT
    assert model_for_objective(TradingObjective.PROFIT) is SOL_PROFIT_MODEL
    assert model_for_objective(TradingObjective.WIN_RATE) is SOL_WIN_RATE_MODEL


def test_catalog_exposes_both_choices() -> None:
    rows = list_trading_profiles(selected=TradingObjective.PROFIT)
    assert len(rows) == 2
    by_obj = {r["objective"]: r for r in rows}
    assert by_obj["profit"]["selected"] is True
    assert by_obj["win_rate"]["selected"] is False
    assert by_obj["profit"]["validation"]["win_rate"] == 0.409
    assert by_obj["win_rate"]["validation"]["win_rate"] == 0.589
    assert "Expectancy" in by_obj["profit"]["label"]
    assert "Win rate" in by_obj["win_rate"]["label"]


def test_parse_rejects_unknown() -> None:
    assert parse_trading_objective("win_rate") == TradingObjective.WIN_RATE
    try:
        parse_trading_objective("scalp")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_soak_trade_model_code_never_pools_profiles() -> None:
    from private_trading_paper_trade.service import soak_trade_model_code
    from private_trading_strategies.multi_market import SOL_PROFIT_MODEL, SOL_WIN_RATE_MODEL

    v1 = SOL_PROFIT_MODEL.code
    v2 = SOL_WIN_RATE_MODEL.code
    # Pre-profile rows only carry the freeze stamp (always V1).
    assert soak_trade_model_code({"soak_freeze_model": v1}) == v1
    # paper_model_code wins over the freeze stamp.
    assert soak_trade_model_code({"soak_freeze_model": v1, "paper_model_code": v2}) == v2
    assert soak_trade_model_code({}) is None
    assert soak_trade_model_code(None) is None
