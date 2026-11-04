from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from private_trading_agents.coin_desk import (
    COIN_CONTEXT,
    coin_role,
    describe_coin,
    narrate_coin,
    narrate_desk,
    resolve_coin,
)
from private_trading_notifications.bot import handle_update
from private_trading_strategies.multi_market import PAPER_MODEL_REGISTRY, TradingObjective
from tests.unit.test_telegram import FakeRepo, _message, _owner_account

NOW = datetime(2026, 11, 3, 12, 5, tzinfo=UTC)
CANDLE = datetime(2026, 11, 3, 11, 0, tzinfo=UTC)
PROFIT = TradingObjective.PROFIT
SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT")


def _run(action: str, status: str = "completed", **details: Any) -> dict[str, Any]:
    return {"candle_open_time": CANDLE, "status": status, "action": action, "details": details}


def _describe(symbol: str, **kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "objective": PROFIT,
        "last_run": None,
        "open_trade": None,
        "portfolio_row": None,
        "auto_open_enabled": True,
        "now": NOW,
    }
    args.update(kw)
    return describe_coin(symbol, **args)


def test_roles_follow_the_registry() -> None:
    assert coin_role("SOL/USDT", PROFIT)["role"] == "paper"
    assert coin_role("DOGE/USDT", PROFIT)["role"] == "paper"
    assert coin_role("BTC/USDT", PROFIT)["role"] == "watch"
    assert coin_role("ETH/USDT", PROFIT)["role"] == "watch"
    # Watch coins really have no registry model.
    assert not [s for s in PAPER_MODEL_REGISTRY if s.symbol in ("BTC/USDT", "ETH/USDT")]


def test_win_rate_profile_says_doge_goes_wait() -> None:
    role = coin_role("DOGE/USDT", TradingObjective.WIN_RATE)
    assert role["role"] == "inactive_for_profile"
    assert "stays WAIT" in role["note"]
    assert coin_role("SOL/USDT", TradingObjective.WIN_RATE)["role"] == "paper"


def test_watch_coin_wait_is_labelled_watch_with_context() -> None:
    coin = _describe("BTC/USDT", last_run=_run("WAIT", "no_validated_model",
                                                 notes=["regime=trend_up"]))
    assert coin["headline"] == "WATCH"
    assert "No validated paper model" in coin["reasons"][0]
    assert "Current regime: trend_up." in coin["reasons"]
    assert "failed after costs" in coin["context"]


def test_wait_explains_blockers_in_plain_language() -> None:
    coin = _describe("SOL/USDT", last_run=_run("WAIT", reasons=["volume_gate_failed"]))
    assert coin["headline"] == "WAIT"
    assert coin["reasons"] == ["Volume did not confirm (no effort behind the move)."]


def test_enter_blocked_by_pause_is_explicit() -> None:
    coin = _describe(
        "SOL/USDT",
        last_run=_run("ENTER", paper_open_blocked="PAPER_AUTO_OPEN_PAUSED",
                      levels={"entry": "150", "stop": "145", "target": "165", "rr": "3"}),
        auto_open_enabled=False,
    )
    assert coin["headline"] == "ENTER (not opened)"
    assert any("paused" in r for r in coin["reasons"])
    assert "entry 150, stop 145, target 165" in narrate_coin(coin)


def test_open_trade_takes_precedence_and_portfolio_note_is_skipped() -> None:
    coin = _describe(
        "SOL/USDT",
        last_run=_run("WAIT"),
        open_trade={"status": "open", "direction": "long", "model_code": "sol-v1",
                    "entry": "150", "stop": "145", "target": "165"},
        portfolio_row={"portfolio_allows_open": False, "blockers": ["symbol_already_open"]},
    )
    assert coin["headline"] == "IN PAPER TRADE"
    assert not any("Portfolio would refuse" in r for r in coin["reasons"])


def test_portfolio_refusal_is_explained_for_flat_coin() -> None:
    coin = _describe(
        "DOGE/USDT",
        last_run=_run("NO_SETUP", "prefilter_no_setup"),
        portfolio_row={"portfolio_allows_open": False,
                       "blockers": ["crypto_cluster_risk_exceeded"]},
    )
    assert any("crypto cluster cap is full" in r for r in coin["reasons"])


def test_old_scan_is_flagged() -> None:
    old = _run("WAIT")
    old["candle_open_time"] = NOW - timedelta(hours=6)
    coin = _describe("SOL/USDT", last_run=old)
    assert any("is the scanner running" in r for r in coin["reasons"])


def test_resolve_coin_accepts_short_names() -> None:
    assert resolve_coin("sol", SYMBOLS) == "SOL/USDT"
    assert resolve_coin("DOGE-USDT", SYMBOLS) == "DOGE/USDT"
    assert resolve_coin("xrp", SYMBOLS) is None


def _view() -> dict[str, Any]:
    coins = [
        _describe("BTC/USDT", last_run=_run("WAIT", "no_validated_model")),
        _describe("ETH/USDT"),
        _describe("SOL/USDT", last_run=_run("ENTER", paper_trade_id="x")),
        _describe("DOGE/USDT", last_run=_run("NO_SETUP", "prefilter_no_setup")),
    ]
    return {
        "profile": {"objective": "profit", "model_code": "sol-v1"},
        "supervisor": {"paper_auto_open_enabled": True, "pause_reasons": []},
        "soak": {"model_code": "sol-v1", "closed_trades": 3, "min_closed_trades": 20,
                 "mean_r": 0.4},
        "coins": coins,
        "authorizes_trade": False,
    }


def test_desk_narration_covers_every_coin() -> None:
    text = narrate_desk(_view())
    for symbol in SYMBOLS:
        assert symbol in text
    assert "3/20 closed" in text
    assert "not a trade instruction" in text
    assert set(COIN_CONTEXT) == set(SYMBOLS)


class DeskRepo(FakeRepo):
    async def coin_desk(self, *, user_id: Any) -> dict[str, Any]:
        self.calls.append("coin_desk")
        return _view()


@pytest.mark.asyncio
async def test_telegram_coins_and_why_commands() -> None:
    repo = DeskRepo(linked={42: _owner_account()})
    coins = await handle_update(_message("/coins"), repo)
    assert coins.handled == "coins"
    assert "DOGE/USDT" in coins.replies[0].text

    why = await handle_update(_message("/why sol"), repo)
    assert why.handled == "why" and why.meta["symbol"] == "SOL/USDT"
    assert "SOL/USDT" in why.replies[0].text

    usage = await handle_update(_message("/why xrp"), repo)
    assert usage.handled == "why_usage"
