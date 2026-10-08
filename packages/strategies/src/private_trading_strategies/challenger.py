"""Research challengers that may enter paper soak but cannot authorize live alerts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ChallengerSpec:
    code: str
    version_no: int
    symbol: str
    direction: str
    higher_timeframe: str
    entry_timeframe: str
    ema_periods: tuple[int, int, int]
    require_rising_slow_ema: bool
    volume_ratio_min: float
    target_r: float
    max_bars_in_trade: int
    max_breakout_extension_atr: float
    paper_only: bool
    live_alerts_allowed: bool


SOL_MTF_CHALLENGER_V1 = ChallengerSpec(
    code="sol-mtf-bos-volume",
    version_no=1,
    symbol="SOL/USDT",
    direction="long",
    higher_timeframe="4h",
    entry_timeframe="1h",
    ema_periods=(12, 21, 50),
    require_rising_slow_ema=True,
    volume_ratio_min=2.0,
    target_r=3.0,
    max_bars_in_trade=80,
    max_breakout_extension_atr=2.0,
    paper_only=True,
    live_alerts_allowed=False,
)
