from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from private_trading_risk.types import Direction, InstrumentRiskMeta


def risk_reward(
    *,
    direction: Direction,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (risk_distance, reward_distance, rr_ratio)."""
    if direction == Direction.LONG:
        risk = entry - stop
        reward = target - entry
    else:
        risk = stop - entry
        reward = entry - target
    if risk <= 0:
        raise ValueError("non_positive_risk_distance")
    if reward <= 0:
        raise ValueError("non_positive_reward_distance")
    return risk, reward, (reward / risk)


def stop_is_valid_for_direction(
    *,
    direction: Direction,
    entry: Decimal,
    stop: Decimal,
) -> bool:
    if direction == Direction.LONG:
        return stop < entry
    return stop > entry


def round_to_tick(price: Decimal, tick: Decimal | None) -> Decimal:
    if tick is None or tick <= 0:
        return price
    steps = (price / tick).to_integral_value(rounding=ROUND_DOWN)
    return steps * tick


def round_to_step(qty: Decimal, step: Decimal | None) -> Decimal:
    if step is None or step <= 0:
        return qty
    steps = (qty / step).to_integral_value(rounding=ROUND_DOWN)
    return steps * step


def paper_quantity(
    *,
    equity: Decimal,
    risk_pct: Decimal,
    entry: Decimal,
    stop: Decimal,
    instrument: InstrumentRiskMeta | None,
) -> tuple[Decimal | None, Decimal | None, list[str]]:
    """Suggest paper size only — never submits live orders."""
    notes: list[str] = []
    if equity <= 0 or risk_pct <= 0:
        return None, None, ["invalid_equity_or_risk_pct"]
    risk_amount = equity * (risk_pct / Decimal("100"))
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0:
        return None, None, ["invalid_risk_per_unit"]
    qty = risk_amount / risk_per_unit
    if instrument and instrument.asset_class.lower() == "crypto":
        qty = round_to_step(qty, instrument.qty_step)
        notes.append("rounded_to_qty_step")
    elif instrument and instrument.asset_class.lower() in {"fx", "forex"}:
        # Scaffolding: convert to lots if lot_size known
        if instrument.lot_size and instrument.lot_size > 0:
            lots = (qty / instrument.lot_size).to_integral_value(rounding=ROUND_DOWN)
            qty = lots * instrument.lot_size
            notes.append("fx_lot_scaffolding")
        else:
            notes.append("fx_lot_size_unknown")
    notional = qty * entry if qty is not None else None
    if (
        instrument
        and instrument.min_notional is not None
        and notional is not None
        and notional < instrument.min_notional
    ):
        notes.append("below_min_notional")
    return qty, notional, notes
