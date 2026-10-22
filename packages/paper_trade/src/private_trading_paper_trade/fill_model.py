"""Stored fill-model assumptions. Same engine knobs as backtest — never look-ahead."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from private_trading_backtest.costs import apply_entry_price, apply_exit_price, cost_amount
from private_trading_backtest.types import CostModel

PAPER_ENGINE_VERSION = "0.1.0"
PAPER_LABEL = "PAPER"

DEFAULT_FILL_MODEL: dict[str, Any] = {
    "label": PAPER_LABEL,
    "fill_policy": "next_open",
    "same_candle_ambiguity": "conservative_stop_first",
    "fee_bps": "10",
    "slippage_bps": "5",
    "spread_bps": "2",
    "max_bars_in_trade": 20,
    "risk_pct": "0.5",
    "engine_version": PAPER_ENGINE_VERSION,
    "notes": [
        "Signal on closed bar i fills at bar i+1 open only.",
        "If stop and target both touch on the same bar, stop wins (conservative).",
        "PAPER — decision support simulation, not live execution.",
    ],
}


def default_fill_model(**overrides: Any) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_FILL_MODEL)
    cfg.update(overrides)
    cfg["label"] = PAPER_LABEL
    return cfg


def cost_model_from(fill_model: dict[str, Any]) -> CostModel:
    return CostModel(
        fee_bps=Decimal(str(fill_model.get("fee_bps", "10"))),
        slippage_bps=Decimal(str(fill_model.get("slippage_bps", "5"))),
        spread_bps=Decimal(str(fill_model.get("spread_bps", "2"))),
    )


def max_bars(fill_model: dict[str, Any]) -> int:
    return int(fill_model.get("max_bars_in_trade") or 20)


def risk_pct(fill_model: dict[str, Any]) -> Decimal:
    return Decimal(str(fill_model.get("risk_pct") or "0.5"))


def entry_fill(raw_open: Decimal, *, direction: str, fill_model: dict[str, Any]) -> Decimal:
    return apply_entry_price(raw_open, direction=direction, costs=cost_model_from(fill_model))


def exit_fill(raw: Decimal, *, direction: str, fill_model: dict[str, Any]) -> Decimal:
    return apply_exit_price(raw, direction=direction, costs=cost_model_from(fill_model))


def round_trip_costs(
    *, entry: Decimal, exit_price: Decimal, qty: Decimal, fill_model: dict[str, Any]
) -> Decimal:
    costs = cost_model_from(fill_model)
    return cost_amount(entry * qty, costs=costs) + cost_amount(exit_price * qty, costs=costs)


def assumed_fill_bps(fill_model: dict[str, Any]) -> Decimal:
    costs = cost_model_from(fill_model)
    return costs.slippage_bps + (costs.spread_bps / Decimal("2"))


def adverse_bps(*, planned: Decimal, actual: Decimal, direction: str) -> Decimal | None:
    if planned <= 0:
        return None
    delta = (actual - planned) / planned * Decimal("10000")
    if direction == "long":
        return delta
    return -delta


def soak_fill_diagnostics(
    *,
    direction: str,
    planned_entry: Decimal,
    raw_open: Decimal | None,
    filled_price: Decimal,
    fill_model: dict[str, Any],
) -> dict[str, str]:
    """Compare paper fill to the freeze's research SOL fill assumption."""
    assumed = assumed_fill_bps(fill_model)
    research = Decimal(str(fill_model.get("research_pair_fill_bps") or "8"))
    vs_plan = adverse_bps(
        planned=planned_entry, actual=filled_price, direction=direction
    )
    vs_open = (
        None
        if raw_open is None
        else adverse_bps(planned=raw_open, actual=filled_price, direction=direction)
    )
    extra = None if vs_open is None else vs_open - research
    return {
        "planned_entry": str(planned_entry),
        "raw_next_open": None if raw_open is None else str(raw_open),
        "filled_price": str(filled_price),
        "assumed_fill_bps": str(assumed),
        "realized_fill_bps_vs_open": None if vs_open is None else str(vs_open),
        "adverse_bps_vs_planned": None if vs_plan is None else str(vs_plan),
        "research_pair_fill_bps": str(research),
        "extra_cost_bps_vs_research": None if extra is None else str(extra),
    }
