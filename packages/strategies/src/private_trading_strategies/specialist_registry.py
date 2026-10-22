"""Validated specialist registry.

The registry is intentionally empty until a new specialist clears absolute
promotion gates and beats the incumbent. Research outcomes live in the
findings document; failed models must never become runtime routes.
"""

from __future__ import annotations

from dataclasses import dataclass

from private_trading_strategies.multi_market import (
    MarketRegime,
    TradingObjective,
    ValidationStats,
)
from private_trading_strategies.specialists import SpecialistConfig


@dataclass(slots=True, frozen=True)
class ValidatedSpecialistModel:
    config: SpecialistConfig
    objective: TradingObjective
    regimes: tuple[MarketRegime, ...]
    validation: ValidationStats
    paper_only: bool = True
    live_alerts_allowed: bool = False


VALIDATED_SPECIALIST_MODELS: tuple[ValidatedSpecialistModel, ...] = ()


def resolve_specialist_model(
    *,
    symbol: str,
    regime: MarketRegime,
    objective: TradingObjective,
) -> ValidatedSpecialistModel | None:
    for model in VALIDATED_SPECIALIST_MODELS:
        if (
            model.config.symbol == symbol
            and model.objective == objective
            and regime in model.regimes
            and model.paper_only
            and not model.live_alerts_allowed
        ):
            return model
    return None
