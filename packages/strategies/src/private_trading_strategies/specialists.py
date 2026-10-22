"""Deterministic pair-specialist strategy plugins.

Every plugin consumes completed bars only and returns WAIT when required
evidence is unavailable. The same evaluator is reusable by research and paper
scanning so model selection cannot silently change signal semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from private_trading_features.specialist import (
    atr_at,
    beta_adjusted_return,
    ema_at,
    in_liquid_forex_session,
    relative_strength,
    rolling_extreme,
    volatility_ratio,
)
from private_trading_features.types import CandleBar

from private_trading_strategies.multi_market import MarketRegime


class StrategyFamily(StrEnum):
    TREND_BREAKOUT = "trend_breakout"
    PULLBACK_CONTINUATION = "pullback_continuation"
    VOLATILITY_EXPANSION = "volatility_expansion"
    RELATIVE_STRENGTH = "relative_strength"
    RANGE_REVERSION = "range_reversion"
    SESSION_BREAKOUT = "session_breakout"
    SESSION_PULLBACK = "session_pullback"


class SpecialistAction(StrEnum):
    ENTER = "ENTER"
    WAIT = "WAIT"


@dataclass(slots=True, frozen=True)
class SpecialistConfig:
    code: str
    family: StrategyFamily
    symbol: str
    asset_class: str
    allowed_regimes: tuple[MarketRegime, ...]
    rr: Decimal
    max_bars: int
    breakout_lookback: int = 20
    stop_lookback: int = 10
    volume_ratio_min: Decimal | None = None
    relative_strength_min: Decimal = Decimal("0.01")
    pullback_tolerance_atr: Decimal = Decimal("0.25")
    range_entry_atr: Decimal = Decimal("1")
    partial_at_r: Decimal | None = None
    partial_fraction: Decimal = Decimal("0")
    use_beta_adjustment: bool = False


@dataclass(slots=True, frozen=True)
class SpecialistContext:
    entry_bars: list[CandleBar]
    higher_timeframe_bars: list[CandleBar]
    regime: MarketRegime
    benchmark_bars: list[CandleBar] | None = None


@dataclass(slots=True, frozen=True)
class SpecialistSignal:
    action: SpecialistAction
    family: StrategyFamily
    config_code: str
    direction: str | None = None
    entry_reference: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    reason: str | None = None


TREND_REGIMES = (
    MarketRegime.TREND_HIGH_VOL,
    MarketRegime.TREND_LOW_VOL,
)
RANGE_REGIMES = (
    MarketRegime.RANGE_HIGH_VOL,
    MarketRegime.RANGE_LOW_VOL,
)


_FOREX_FAMILIES = (
    StrategyFamily.SESSION_BREAKOUT,
    StrategyFamily.SESSION_PULLBACK,
    StrategyFamily.RANGE_REVERSION,
)

SPECIALIST_FAMILIES_BY_SYMBOL: dict[str, tuple[StrategyFamily, ...]] = {
    "BTC/USDT": (
        StrategyFamily.TREND_BREAKOUT,
        StrategyFamily.PULLBACK_CONTINUATION,
        StrategyFamily.VOLATILITY_EXPANSION,
    ),
    "ETH/USDT": (
        StrategyFamily.RELATIVE_STRENGTH,
        StrategyFamily.TREND_BREAKOUT,
        StrategyFamily.PULLBACK_CONTINUATION,
    ),
    "BNB/USDT": (
        StrategyFamily.TREND_BREAKOUT,
        StrategyFamily.PULLBACK_CONTINUATION,
        StrategyFamily.RANGE_REVERSION,
    ),
    "SOL/USDT": (
        StrategyFamily.TREND_BREAKOUT,
        StrategyFamily.VOLATILITY_EXPANSION,
        StrategyFamily.PULLBACK_CONTINUATION,
    ),
    "EUR/USD": _FOREX_FAMILIES,
    "GBP/USD": _FOREX_FAMILIES,
    "USD/JPY": _FOREX_FAMILIES,
    "USD/CHF": _FOREX_FAMILIES,
    "AUD/USD": _FOREX_FAMILIES,
    "USD/CAD": _FOREX_FAMILIES,
    "NZD/USD": _FOREX_FAMILIES,
    "EUR/GBP": _FOREX_FAMILIES,
}


def _wait(config: SpecialistConfig, reason: str) -> SpecialistSignal:
    return SpecialistSignal(
        action=SpecialistAction.WAIT,
        family=config.family,
        config_code=config.code,
        reason=reason,
    )


def _signal(
    config: SpecialistConfig,
    *,
    direction: str,
    entry: Decimal,
    stop: Decimal,
) -> SpecialistSignal:
    if config.asset_class == "crypto" and direction == "short":
        return _wait(config, "spot_crypto_short_not_allowed")
    risk = abs(entry - stop)
    if risk <= 0:
        return _wait(config, "invalid_risk_geometry")
    sign = Decimal("1") if direction == "long" else Decimal("-1")
    return SpecialistSignal(
        action=SpecialistAction.ENTER,
        family=config.family,
        config_code=config.code,
        direction=direction,
        entry_reference=entry,
        stop_price=stop,
        target_price=entry + sign * risk * config.rr,
    )


def _higher_timeframe_direction(bars: list[CandleBar]) -> str | None:
    index = len(bars) - 1
    current = ema_at(bars, index, 50)
    prior = ema_at(bars, index - 5, 50)
    if current is None or prior is None:
        return None
    close = bars[index].close
    if close > current > prior:
        return "long"
    if close < current < prior:
        return "short"
    return None


def _volume_passes(config: SpecialistConfig, bars: list[CandleBar], index: int) -> bool:
    if config.volume_ratio_min is None:
        return True
    if index < 20 or bars[index].volume is None:
        return False
    volumes = [bar.volume for bar in bars[index - 19 : index + 1]]
    if any(value is None for value in volumes):
        return False
    average = sum((value for value in volumes if value is not None), Decimal("0")) / Decimal(
        20
    )
    if average <= 0:
        return False
    return bars[index].volume / average >= config.volume_ratio_min


def _trend_breakout(
    config: SpecialistConfig, context: SpecialistContext
) -> SpecialistSignal:
    direction = _higher_timeframe_direction(context.higher_timeframe_bars)
    bars = context.entry_bars
    index = len(bars) - 1
    if direction is None:
        return _wait(config, "higher_timeframe_trend_unknown")
    if not _volume_passes(config, bars, index):
        return _wait(config, "volume_gate_failed")
    high = rolling_extreme(bars, index, config.breakout_lookback, side="high")
    low = rolling_extreme(bars, index, config.breakout_lookback, side="low")
    stop_low = rolling_extreme(bars, index, config.stop_lookback, side="low")
    stop_high = rolling_extreme(bars, index, config.stop_lookback, side="high")
    close = bars[index].close
    if direction == "long" and high is not None and stop_low is not None and close > high:
        return _signal(config, direction=direction, entry=close, stop=stop_low)
    if direction == "short" and low is not None and stop_high is not None and close < low:
        return _signal(config, direction=direction, entry=close, stop=stop_high)
    return _wait(config, "breakout_not_confirmed")


def _pullback(
    config: SpecialistConfig, context: SpecialistContext
) -> SpecialistSignal:
    direction = _higher_timeframe_direction(context.higher_timeframe_bars)
    bars = context.entry_bars
    index = len(bars) - 1
    average = ema_at(bars, index, 21)
    atr = atr_at(bars, index)
    if direction is None or average is None or atr is None:
        return _wait(config, "pullback_inputs_unknown")
    tolerance = atr * config.pullback_tolerance_atr
    bar = bars[index]
    stop = rolling_extreme(
        bars,
        index,
        config.stop_lookback,
        side="low" if direction == "long" else "high",
    )
    if stop is None:
        return _wait(config, "stop_unknown")
    if (
        direction == "long"
        and bar.low <= average + tolerance
        and bar.close > average
        and bar.close > bar.open
    ):
        return _signal(config, direction=direction, entry=bar.close, stop=stop)
    if (
        direction == "short"
        and bar.high >= average - tolerance
        and bar.close < average
        and bar.close < bar.open
    ):
        return _signal(config, direction=direction, entry=bar.close, stop=stop)
    return _wait(config, "pullback_not_confirmed")


def _volatility_expansion(
    config: SpecialistConfig, context: SpecialistContext
) -> SpecialistSignal:
    bars = context.entry_bars
    index = len(bars) - 1
    current = volatility_ratio(bars, index)
    prior = volatility_ratio(bars, index - 5)
    if current is None or prior is None or prior >= Decimal("0.9") or current <= Decimal("1"):
        return _wait(config, "no_contraction_expansion")
    return _trend_breakout(config, context)


def _relative_strength(
    config: SpecialistConfig, context: SpecialistContext
) -> SpecialistSignal:
    if context.benchmark_bars is None:
        return _wait(config, "benchmark_missing")
    index = len(context.entry_bars) - 1
    if config.use_beta_adjustment:
        strength = beta_adjusted_return(
            context.entry_bars,
            context.benchmark_bars,
            index,
            config.breakout_lookback,
        )
        if strength is None or strength < config.relative_strength_min:
            return _wait(config, "beta_adjusted_momentum_below_minimum")
    else:
        strength = relative_strength(
            context.entry_bars,
            context.benchmark_bars,
            index,
            config.breakout_lookback,
        )
        if strength is None or strength < config.relative_strength_min:
            return _wait(config, "relative_strength_below_minimum")
    signal = _trend_breakout(config, context)
    if signal.direction == "short":
        return _wait(config, "relative_strength_long_only")
    return signal


def _range_reversion(
    config: SpecialistConfig, context: SpecialistContext
) -> SpecialistSignal:
    bars = context.entry_bars
    index = len(bars) - 1
    average = ema_at(bars, index, 50)
    atr = atr_at(bars, index)
    if average is None or atr is None:
        return _wait(config, "range_inputs_unknown")
    bar = bars[index]
    distance = config.range_entry_atr * atr
    if bar.close < average - distance and bar.close > bar.open:
        return _signal(
            config,
            direction="long",
            entry=bar.close,
            stop=bar.low - atr * Decimal("0.5"),
        )
    if bar.close > average + distance and bar.close < bar.open:
        return _signal(
            config,
            direction="short",
            entry=bar.close,
            stop=bar.high + atr * Decimal("0.5"),
        )
    return _wait(config, "range_reversal_not_confirmed")


def _session_breakout(
    config: SpecialistConfig, context: SpecialistContext
) -> SpecialistSignal:
    bars = context.entry_bars
    index = len(bars) - 1
    if not in_liquid_forex_session(bars[index].open_time.hour):
        return _wait(config, "outside_liquid_forex_session")
    direction = _higher_timeframe_direction(context.higher_timeframe_bars)
    if direction is None:
        return _wait(config, "daily_trend_unknown")
    return _trend_breakout(config, context)


def evaluate_specialist(
    config: SpecialistConfig, context: SpecialistContext
) -> SpecialistSignal:
    if not context.entry_bars or not context.higher_timeframe_bars:
        return _wait(config, "missing_bars")
    if not context.entry_bars[-1].is_final or not context.higher_timeframe_bars[-1].is_final:
        return _wait(config, "bar_not_final")
    if context.regime not in config.allowed_regimes:
        return _wait(config, "regime_not_allowed")
    if config.symbol not in SPECIALIST_FAMILIES_BY_SYMBOL:
        return _wait(config, "symbol_not_supported")
    if config.family not in SPECIALIST_FAMILIES_BY_SYMBOL[config.symbol]:
        return _wait(config, "family_not_allowed_for_symbol")

    if config.family == StrategyFamily.TREND_BREAKOUT:
        return _trend_breakout(config, context)
    if config.family in {
        StrategyFamily.PULLBACK_CONTINUATION,
        StrategyFamily.SESSION_PULLBACK,
    }:
        if (
            config.family == StrategyFamily.SESSION_PULLBACK
            and not in_liquid_forex_session(context.entry_bars[-1].open_time.hour)
        ):
            return _wait(config, "outside_liquid_forex_session")
        return _pullback(config, context)
    if config.family == StrategyFamily.VOLATILITY_EXPANSION:
        return _volatility_expansion(config, context)
    if config.family == StrategyFamily.RELATIVE_STRENGTH:
        return _relative_strength(config, context)
    if config.family == StrategyFamily.RANGE_REVERSION:
        return _range_reversion(config, context)
    if config.family == StrategyFamily.SESSION_BREAKOUT:
        return _session_breakout(config, context)
    return _wait(config, "family_not_implemented")
