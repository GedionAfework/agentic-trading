from decimal import Decimal

import pytest
from private_trading_agents.contracts import AgentId
from private_trading_agents.roles.ag06_risk import run_portfolio_status
from private_trading_agents.tools import ToolId
from private_trading_agents.tools.errors import ToolPermissionError
from private_trading_agents.tools.permissions import has_permission
from private_trading_agents.tools.runtime import invoke_tool
from private_trading_risk.portfolio import (
    OpenExposure,
    PortfolioRiskInput,
    assess_portfolio_risk,
    portfolio_headroom,
)

COINS = {
    "BTC/USDT": Decimal("0.5"),
    "ETH/USDT": Decimal("0.5"),
    "SOL/USDT": Decimal("0.5"),
    "DOGE/USDT": Decimal("0.5"),
}


def _sol_open() -> tuple[OpenExposure, ...]:
    return (OpenExposure("SOL/USDT", "crypto", "long", Decimal("0.5")),)


def _verdicts(view: dict) -> dict[str, dict]:
    return {row["symbol"]: row for row in view["symbols"]}


def test_empty_book_has_room_for_every_coin() -> None:
    view = portfolio_headroom(
        open_exposures=(), daily_realized_pnl_pct=Decimal("0"), candidates=COINS
    )
    assert view["crypto_headroom_pct"] == "1"
    assert all(row["portfolio_allows_open"] for row in view["symbols"])
    assert view["authorizes_trade"] is False


def test_sol_open_blocks_sol_and_leaves_one_crypto_slot() -> None:
    view = portfolio_headroom(
        open_exposures=_sol_open(), daily_realized_pnl_pct=Decimal("0"), candidates=COINS
    )
    rows = _verdicts(view)
    assert rows["SOL/USDT"]["blockers"] == ["symbol_already_open"]
    assert rows["DOGE/USDT"]["portfolio_allows_open"] is True
    assert view["crypto_headroom_pct"] == "0.5"


def test_sol_and_doge_open_fill_the_crypto_cluster() -> None:
    book = _sol_open() + (OpenExposure("DOGE/USDT", "crypto", "long", Decimal("0.5")),)
    rows = _verdicts(
        portfolio_headroom(
            open_exposures=book, daily_realized_pnl_pct=Decimal("0"), candidates=COINS
        )
    )
    assert "crypto_cluster_risk_exceeded" in rows["BTC/USDT"]["blockers"]
    assert "crypto_cluster_risk_exceeded" in rows["ETH/USDT"]["blockers"]


def test_daily_loss_stop_blocks_everything() -> None:
    view = portfolio_headroom(
        open_exposures=(), daily_realized_pnl_pct=Decimal("-1.5"), candidates=COINS
    )
    assert view["daily_loss_stop_hit"] is True
    assert all("daily_loss_stop" in row["blockers"] for row in view["symbols"])


@pytest.mark.parametrize("pnl", [Decimal("0"), Decimal("-2")])
def test_view_never_disagrees_with_real_gate(pnl: Decimal) -> None:
    book = _sol_open()
    view = portfolio_headroom(open_exposures=book, daily_realized_pnl_pct=pnl, candidates=COINS)
    for row in view["symbols"]:
        real = assess_portfolio_risk(
            PortfolioRiskInput(
                proposed_symbol=row["symbol"],
                proposed_asset_class="crypto",
                proposed_direction="long",
                proposed_risk_pct=COINS[row["symbol"]],
                open_exposures=book,
                daily_realized_pnl_pct=pnl,
            )
        )
        assert row["portfolio_allows_open"] == real.approved
        assert row["blockers"] == real.blockers


def test_ag06_tool_explains_without_authorizing() -> None:
    out = run_portfolio_status(
        {
            "open_exposures": [
                {"symbol": "SOL/USDT", "risk_pct": "0.5"},
                {"symbol": "DOGE/USDT", "risk_pct": "0.5"},
            ],
            "candidates": {k: str(v) for k, v in COINS.items()},
        }
    )
    assert out.authorizes_trade is False
    assert out.crypto_headroom_pct == "0"
    assert "BTC/USDT: blocked, the crypto cluster cap is full" in out.explanation
    assert "SOL/USDT: blocked, a position is already open" in out.explanation


def test_portfolio_tool_is_ag06_only() -> None:
    assert has_permission(AgentId.AG06_RISK, ToolId.RISK_PORTFOLIO_STATUS)
    for agent in AgentId:
        if agent != AgentId.AG06_RISK:
            assert not has_permission(agent, ToolId.RISK_PORTFOLIO_STATUS)
    with pytest.raises(ToolPermissionError):
        invoke_tool(
            agent=AgentId.AG01_ORCHESTRATOR,
            tool=ToolId.RISK_PORTFOLIO_STATUS,
            payload={},
        )


def test_portfolio_tool_rejects_unknown_fields() -> None:
    with pytest.raises(Exception):  # noqa: B017 — pydantic extra=forbid
        run_portfolio_status({"open_exposures": [], "authorize": True})
