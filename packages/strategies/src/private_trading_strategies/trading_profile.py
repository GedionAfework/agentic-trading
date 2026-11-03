"""Client-selectable paper trading profiles (frozen SOL V1 / V2).

These are not newly trained models. The client picks which validated
incumbent drives scanning and paper opens.
"""

from __future__ import annotations

from typing import Any

from private_trading_strategies.multi_market import (
    SOL_PROFIT_MODEL,
    SOL_WIN_RATE_MODEL,
    MarketModelSpec,
    TradingObjective,
)

# Default when no preference is stored (matches soak freeze).
DEFAULT_TRADING_OBJECTIVE = TradingObjective.PROFIT

_CHOICES: tuple[MarketModelSpec, ...] = (SOL_PROFIT_MODEL, SOL_WIN_RATE_MODEL)

_CLIENT_COPY: dict[TradingObjective, dict[str, str]] = {
    TradingObjective.PROFIT: {
        "label": "Expectancy (V1)",
        "summary": "Fewer wins, higher average R. Active soak default.",
    },
    TradingObjective.WIN_RATE: {
        "label": "Win rate (V2)",
        "summary": "More wins via scale-out exits; lower average R.",
    },
}


def model_for_objective(objective: TradingObjective) -> MarketModelSpec:
    for spec in _CHOICES:
        if spec.objective == objective:
            return spec
    raise ValueError(f"no choosable paper model for objective={objective}")


def list_trading_profiles(*, selected: TradingObjective | None = None) -> list[dict[str, Any]]:
    """Catalog for the client picker."""
    active = selected or DEFAULT_TRADING_OBJECTIVE
    rows: list[dict[str, Any]] = []
    for spec in _CHOICES:
        copy = _CLIENT_COPY[spec.objective]
        rows.append(
            {
                "objective": spec.objective.value,
                "code": spec.code,
                "version_no": spec.version_no,
                "symbol": spec.symbol,
                "label": copy["label"],
                "summary": copy["summary"],
                "selected": spec.objective == active,
                "paper_only": spec.paper_only,
                "live_alerts_allowed": spec.live_alerts_allowed,
                "validation": {
                    "trades": spec.validation.trades,
                    "win_rate": spec.validation.win_rate,
                    "mean_r": spec.validation.mean_r,
                    "profit_factor": spec.validation.profit_factor,
                    "method": spec.validation.method,
                },
            }
        )
    return rows


def parse_trading_objective(raw: str) -> TradingObjective:
    try:
        objective = TradingObjective(raw.strip())
    except ValueError as exc:
        raise ValueError(f"unknown trading objective: {raw!r}") from exc
    model_for_objective(objective)  # ensure choosable
    return objective
