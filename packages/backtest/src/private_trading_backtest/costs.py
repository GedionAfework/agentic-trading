from __future__ import annotations

from decimal import Decimal

from private_trading_backtest.types import CostModel


def apply_entry_price(raw: Decimal, *, direction: str, costs: CostModel) -> Decimal:
    # Fill degradation is slippage + half-spread. Fees are cash costs below.
    bps = costs.slippage_bps + (costs.spread_bps / Decimal("2"))
    mult = bps / Decimal("10000")
    if direction == "long":
        return raw * (Decimal("1") + mult)
    return raw * (Decimal("1") - mult)


def apply_exit_price(raw: Decimal, *, direction: str, costs: CostModel) -> Decimal:
    bps = costs.slippage_bps + (costs.spread_bps / Decimal("2"))
    mult = bps / Decimal("10000")
    if direction == "long":
        return raw * (Decimal("1") - mult)
    return raw * (Decimal("1") + mult)


def cost_amount(notional: Decimal, *, costs: CostModel, legs: int = 1) -> Decimal:
    return notional * (costs.fee_bps / Decimal("10000")) * Decimal(legs)
