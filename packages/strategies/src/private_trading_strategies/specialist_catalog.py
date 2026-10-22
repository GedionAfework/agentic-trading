"""Small, pre-registered candidate sets for each pair specialist.

The catalog is intentionally bounded. Expanding it requires a new research
version so repeated searches cannot silently overfit the same holdout.
"""

from __future__ import annotations

from decimal import Decimal

from private_trading_strategies.multi_market import MarketRegime
from private_trading_strategies.specialists import (
    RANGE_REGIMES,
    SPECIALIST_FAMILIES_BY_SYMBOL,
    TREND_REGIMES,
    SpecialistConfig,
    StrategyFamily,
)

SPECIALIST_CATALOG_VERSION = "1.0.0"


def _management(family: StrategyFamily) -> tuple[Decimal | None, Decimal]:
    if family in {
        StrategyFamily.PULLBACK_CONTINUATION,
        StrategyFamily.SESSION_PULLBACK,
    }:
        return Decimal("1"), Decimal("0.5")
    return None, Decimal("0")


def _config(
    symbol: str,
    asset_class: str,
    family: StrategyFamily,
    rr: str,
    variant: int,
) -> SpecialistConfig:
    partial_at, partial_fraction = _management(family)
    regimes: tuple[MarketRegime, ...] = (
        RANGE_REGIMES
        if family == StrategyFamily.RANGE_REVERSION
        else TREND_REGIMES
    )
    return SpecialistConfig(
        code=f"{symbol.lower().replace('/', '-')}-{family.value}-v{variant}",
        family=family,
        symbol=symbol,
        asset_class=asset_class,
        allowed_regimes=regimes,
        rr=Decimal(rr),
        max_bars=40 if family == StrategyFamily.RANGE_REVERSION else 80,
        breakout_lookback=12 if variant == 1 else 24,
        stop_lookback=8 if variant == 1 else 16,
        volume_ratio_min=(
            Decimal("1.5") if asset_class == "crypto" else None
        ),
        relative_strength_min=(
            Decimal("0.005") if variant == 1 else Decimal("0.01")
        ),
        pullback_tolerance_atr=(
            Decimal("0.25") if variant == 1 else Decimal("0.5")
        ),
        range_entry_atr=Decimal("1") if variant == 1 else Decimal("1.5"),
        partial_at_r=partial_at,
        partial_fraction=partial_fraction,
        use_beta_adjustment=(
            family == StrategyFamily.RELATIVE_STRENGTH and variant == 2
        ),
    )


def specialist_candidates(symbol: str) -> tuple[SpecialistConfig, ...]:
    families = SPECIALIST_FAMILIES_BY_SYMBOL.get(symbol, ())
    asset_class = "crypto" if symbol.endswith("/USDT") else "forex"
    candidates: list[SpecialistConfig] = []
    for family in families:
        if family == StrategyFamily.RANGE_REVERSION:
            risk_rewards = ("1", "1.5")
        elif family in {
            StrategyFamily.PULLBACK_CONTINUATION,
            StrategyFamily.SESSION_PULLBACK,
        }:
            risk_rewards = ("1.5", "2")
        else:
            risk_rewards = ("2", "3")
        for variant, rr in enumerate(risk_rewards, start=1):
            candidates.append(_config(symbol, asset_class, family, rr, variant))
    return tuple(candidates)
