"""AG-06 portfolio status — read-only view over the real portfolio gate."""

from __future__ import annotations

from private_trading_risk.portfolio import OpenExposure, portfolio_headroom

from private_trading_agents.tools.portfolio_schemas import (
    PortfolioStatusIn,
    PortfolioStatusOut,
    PortfolioSymbolVerdict,
)

_BLOCKER_TEXT = {
    "symbol_already_open": "a position is already open on it",
    "daily_loss_stop": "the daily loss stop is hit",
    "total_open_risk_exceeded": "total open risk would exceed the cap",
    "crypto_cluster_risk_exceeded": "the crypto cluster cap is full (coins move together)",
    "usd_cluster_risk_exceeded": "the USD cluster cap is full",
    "non_positive_proposed_risk": "no positive risk size is configured",
}


def narrate_portfolio(view: dict[str, object]) -> str:
    """Plain-language summary built only from computed fields."""
    lines = [
        f"Open crypto risk {view['crypto_open_risk_pct']}% of "
        f"{view['crypto_cluster_cap_pct']}% cap "
        f"({view['crypto_headroom_pct']}% free); "
        f"total {view['total_open_risk_pct']}% of {view['total_open_risk_cap_pct']}%."
    ]
    if view["daily_loss_stop_hit"]:
        lines.append(
            f"Daily loss stop hit ({view['daily_realized_pnl_pct']}% today): "
            "no new paper opens until the next UTC day."
        )
    for row in view["symbols"]:  # type: ignore[union-attr]
        symbol = row["symbol"]
        if row["portfolio_allows_open"]:
            lines.append(f"{symbol}: portfolio has room (still needs a model ENTER).")
        else:
            reasons = "; ".join(_BLOCKER_TEXT.get(b, b) for b in row["blockers"])
            lines.append(f"{symbol}: blocked, {reasons}.")
    return "\n".join(lines)


def handle_portfolio_status(payload: PortfolioStatusIn) -> PortfolioStatusOut:
    exposures = tuple(
        OpenExposure(
            symbol=item.symbol,
            asset_class=item.asset_class,
            direction=item.direction,
            risk_pct=item.risk_pct,
        )
        for item in payload.open_exposures
    )
    view = portfolio_headroom(
        open_exposures=exposures,
        daily_realized_pnl_pct=payload.daily_realized_pnl_pct,
        candidates=dict(payload.candidates),
    )
    return PortfolioStatusOut(
        total_open_risk_pct=str(view["total_open_risk_pct"]),
        total_headroom_pct=str(view["total_headroom_pct"]),
        crypto_open_risk_pct=str(view["crypto_open_risk_pct"]),
        crypto_headroom_pct=str(view["crypto_headroom_pct"]),
        daily_loss_stop_hit=bool(view["daily_loss_stop_hit"]),
        symbols=[PortfolioSymbolVerdict(**row) for row in view["symbols"]],  # type: ignore[union-attr]
        explanation=narrate_portfolio(view),
        authorizes_trade=False,
    )
