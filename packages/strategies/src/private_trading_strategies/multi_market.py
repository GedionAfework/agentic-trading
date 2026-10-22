"""Paper-only model metadata and fail-closed multi-market routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from private_trading_features.types import CandleBar


class TradingObjective(StrEnum):
    PROFIT = "profit"
    WIN_RATE = "win_rate"


class MarketRegime(StrEnum):
    TREND_HIGH_VOL = "trend_high_vol"
    TREND_LOW_VOL = "trend_low_vol"
    RANGE_HIGH_VOL = "range_high_vol"
    RANGE_LOW_VOL = "range_low_vol"


@dataclass(slots=True, frozen=True)
class ValidationStats:
    trades: int
    win_rate: float
    mean_r: float
    profit_factor: float | None = None
    max_drawdown_r: float | None = None
    method: str = "walk_forward"


@dataclass(slots=True, frozen=True)
class MarketModelSpec:
    code: str
    version_no: int
    symbol: str
    asset_class: str
    objective: TradingObjective
    regimes: tuple[MarketRegime, ...]
    direction: str
    higher_timeframe: str
    entry_timeframe: str
    target_r: float
    max_bars_in_trade: int
    volume_ratio_min: float | None
    partial_profit_at_r: float | None
    partial_profit_fraction: float
    move_stop_to_breakeven_after_partial: bool
    validation: ValidationStats
    paper_only: bool = True
    live_alerts_allowed: bool = False
    validated_for_paper: bool = False


_TREND_REGIMES = (
    MarketRegime.TREND_HIGH_VOL,
    MarketRegime.TREND_LOW_VOL,
)

SOL_PROFIT_MODEL = MarketModelSpec(
    code="sol-mtf-bos-volume-profit",
    version_no=1,
    symbol="SOL/USDT",
    asset_class="crypto",
    objective=TradingObjective.PROFIT,
    regimes=_TREND_REGIMES,
    direction="long",
    higher_timeframe="4h",
    entry_timeframe="1h",
    target_r=3.0,
    max_bars_in_trade=80,
    volume_ratio_min=2.0,
    partial_profit_at_r=None,
    partial_profit_fraction=0.0,
    move_stop_to_breakeven_after_partial=False,
    validation=ValidationStats(
        trades=164,
        win_rate=0.409,
        mean_r=0.215,
        method="fixed_yearly_walk_forward_2022_2026",
    ),
    validated_for_paper=True,
)

SOL_WIN_RATE_MODEL = MarketModelSpec(
    code="sol-mtf-bos-volume-scale-out",
    version_no=2,
    symbol="SOL/USDT",
    asset_class="crypto",
    objective=TradingObjective.WIN_RATE,
    regimes=_TREND_REGIMES,
    direction="long",
    higher_timeframe="4h",
    entry_timeframe="1h",
    target_r=4.0,
    max_bars_in_trade=80,
    volume_ratio_min=2.0,
    partial_profit_at_r=1.25,
    partial_profit_fraction=0.5,
    move_stop_to_breakeven_after_partial=True,
    validation=ValidationStats(
        trades=175,
        win_rate=0.589,
        mean_r=0.059,
        profit_factor=1.14,
        max_drawdown_r=13.02,
        method="yearly_walk_forward_2022_2026",
    ),
    validated_for_paper=True,
)

# Owner 2-week coin test (2026-10-13). Nested WF PASS on DOGE only.
# Paper-only; live alerts still blocked. 2025–2026 folds were negative.
DOGE_PROFIT_MODEL = MarketModelSpec(
    code="doge-mtf-bos-volume-profit",
    version_no=1,
    symbol="DOGE/USDT",
    asset_class="crypto",
    objective=TradingObjective.PROFIT,
    regimes=_TREND_REGIMES,
    direction="long",
    higher_timeframe="4h",
    entry_timeframe="1h",
    target_r=3.0,
    max_bars_in_trade=80,
    volume_ratio_min=2.0,
    partial_profit_at_r=None,
    partial_profit_fraction=0.0,
    move_stop_to_breakeven_after_partial=False,
    validation=ValidationStats(
        trades=133,
        win_rate=0.383,
        mean_r=0.173,
        profit_factor=1.28,
        max_drawdown_r=14.95,
        method="yearly_walk_forward_2022_2026",
    ),
    validated_for_paper=True,
)

PAPER_MODEL_REGISTRY: tuple[MarketModelSpec, ...] = (
    SOL_PROFIT_MODEL,
    SOL_WIN_RATE_MODEL,
    DOGE_PROFIT_MODEL,
)


def resolve_market_model(
    *,
    symbol: str,
    regime: MarketRegime,
    objective: TradingObjective,
) -> MarketModelSpec | None:
    for spec in PAPER_MODEL_REGISTRY:
        if (
            spec.symbol == symbol
            and spec.objective == objective
            and regime in spec.regimes
            and spec.validated_for_paper
            and spec.paper_only
            and not spec.live_alerts_allowed
        ):
            return spec
    return None


def classify_market_regime(
    entry_bars: list[CandleBar],
    higher_timeframe_bars: list[CandleBar],
) -> MarketRegime | None:
    """Classify using closed bars only; return None when history is insufficient."""
    entry = [bar for bar in entry_bars if bar.is_final]
    higher = [bar for bar in higher_timeframe_bars if bar.is_final]
    if len(entry) < 115 or len(higher) < 60:
        return None

    closes = [float(bar.close) for bar in higher]
    ema50 = sum(closes[:50]) / 50.0
    alpha = 2.0 / 51.0
    prior_ema = ema50
    for index, close in enumerate(closes[50:], start=50):
        ema50 = alpha * close + (1.0 - alpha) * ema50
        if index == len(closes) - 6:
            prior_ema = ema50
    trending = (closes[-1] > ema50 > prior_ema) or (
        closes[-1] < ema50 < prior_ema
    )

    true_ranges: list[float] = []
    for index, bar in enumerate(entry):
        high = float(bar.high)
        low = float(bar.low)
        previous = float(entry[index - 1].close) if index else float(bar.open)
        true_ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    recent_atr = sum(true_ranges[-14:]) / 14.0
    baseline_atr = sum(true_ranges[-114:]) / 114.0
    high_volatility = recent_atr >= baseline_atr

    if trending:
        return (
            MarketRegime.TREND_HIGH_VOL
            if high_volatility
            else MarketRegime.TREND_LOW_VOL
        )
    return (
        MarketRegime.RANGE_HIGH_VOL
        if high_volatility
        else MarketRegime.RANGE_LOW_VOL
    )
