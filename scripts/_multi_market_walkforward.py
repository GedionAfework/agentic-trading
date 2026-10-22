"""Asset-aware walk-forward search for the core crypto and forex universe."""

from __future__ import annotations

import asyncio
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import product

from _oos_strategy_search import Series, ema, prior_swings, volume_ratio
from _walkforward_challenger import atr
from private_trading_backtest.walkforward import (
    ResearchObjective,
    ResearchPerformance,
    SelectionPolicy,
    TimeFold,
    combine_performance,
    pair_cost_bps,
    run_walk_forward,
)
from private_trading_db.models.market import Candle, Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_market_data.universe import (
    CORE_CRYPTO_SYMBOLS,
    CORE_FOREX_SYMBOLS,
)
from sqlalchemy import select


@dataclass(slots=True)
class AssetSeries:
    entry: Series
    asset_class: str
    htf_index: list[int | None]
    htf_closes: list[float]
    htf_ema50: list[float | None]
    atr_values: list[float | None]
    volatility_high: list[bool | None]


@dataclass(slots=True, frozen=True)
class MultiMarketConfig:
    volatility_regime: str
    trend_strength: str
    volume_min: float
    rr: float
    partial_at_r: float | None
    partial_fraction: float
    max_bars: int


def _ema_optional(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    valid: list[float] = []
    alpha = 2.0 / (period + 1)
    current: float | None = None
    for i, value in enumerate(values):
        if value is None:
            continue
        valid.append(value)
        if current is None and len(valid) == period:
            current = sum(valid) / period
        elif current is not None:
            current = alpha * value + (1.0 - alpha) * current
        out[i] = current
    return out


def _volatility_regime(
    closes: list[float], atr_values: list[float | None]
) -> list[bool | None]:
    atr_pct = [
        None if value is None or close <= 0 else value / close
        for close, value in zip(closes, atr_values, strict=True)
    ]
    baseline = _ema_optional(atr_pct, 100)
    return [
        None if value is None or average is None else value >= average
        for value, average in zip(atr_pct, baseline, strict=True)
    ]


async def _rows(session, instrument_id, timeframe: str):
    return (
        await session.execute(
            select(Candle)
            .where(
                Candle.instrument_id == instrument_id,
                Candle.timeframe == timeframe,
                Candle.is_final.is_(True),
            )
            .order_by(Candle.open_time)
        )
    ).scalars().all()


async def load_asset_series(session, symbol: str, asset_class: str) -> AssetSeries:
    instrument = (
        await session.execute(
            select(Instrument).where(Instrument.canonical_symbol == symbol)
        )
    ).scalar_one()
    entry_rows = await _rows(session, instrument.id, "1h")
    htf_rows = await _rows(
        session,
        instrument.id,
        "4h" if asset_class == "crypto" else "1d",
    )
    times = [row.open_time for row in entry_rows]
    opens = [float(row.open) for row in entry_rows]
    highs = [float(row.high) for row in entry_rows]
    lows = [float(row.low) for row in entry_rows]
    closes = [float(row.close) for row in entry_rows]
    volumes = [float(row.volume or 0) for row in entry_rows]
    swing_high, swing_low = prior_swings(highs, lows)
    atr_values = atr(highs, lows, closes)
    entry = Series(
        symbol=symbol,
        times=times,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes,
        ema12=ema(closes, 12),
        ema21=ema(closes, 21),
        ema50=ema(closes, 50),
        swing_high=swing_high,
        swing_low=swing_low,
        vol_ratio=volume_ratio(volumes),
    )
    htf_times = [row.open_time for row in htf_rows]
    htf_closes = [float(row.close) for row in htf_rows]
    duration = timedelta(hours=4) if asset_class == "crypto" else timedelta(days=1)
    mapped: list[int | None] = []
    j = -1
    for one_time in times:
        decision_time = one_time + timedelta(hours=1)
        while (
            j + 1 < len(htf_times)
            and htf_times[j + 1] + duration <= decision_time
        ):
            j += 1
        mapped.append(j if j >= 0 else None)
    return AssetSeries(
        entry=entry,
        asset_class=asset_class,
        htf_index=mapped,
        htf_closes=htf_closes,
        htf_ema50=ema(htf_closes, 50),
        atr_values=atr_values,
        volatility_high=_volatility_regime(closes, atr_values),
    )


def _trend_direction(
    series: AssetSeries, index: int, strength: str
) -> str | None:
    htf_index = series.htf_index[index]
    if htf_index is None:
        return None
    lookback = 10 if series.asset_class == "crypto" else 5
    if htf_index < lookback:
        return None
    close = series.htf_closes[htf_index]
    current = series.htf_ema50[htf_index]
    prior = series.htf_ema50[htf_index - lookback]
    if current is None or prior is None:
        return None
    slope_ratio = abs(current - prior) / current if current else 0.0
    minimum = 0.002 if strength == "strong" else 0.0
    if close > current > prior and slope_ratio >= minimum:
        return "long"
    if series.asset_class == "forex" and close < current < prior and slope_ratio >= minimum:
        return "short"
    return None


def _adverse_fill(raw: float, direction: str, entering: bool, symbol: str) -> float:
    multiplier = pair_cost_bps(symbol) / 10_000.0
    adverse_up = (direction == "long") == entering
    return raw * (1.0 + multiplier if adverse_up else 1.0 - multiplier)


def _trade_r(
    *,
    direction: str,
    entry: float,
    exit_price: float,
    risk: float,
    weight: float,
) -> float:
    gross = exit_price - entry if direction == "long" else entry - exit_price
    return weight * gross / risk


def simulate(
    series: AssetSeries,
    cfg: MultiMarketConfig,
    start: datetime,
    end: datetime,
) -> ResearchPerformance:
    bars = series.entry
    first = bisect_left(bars.times, start)
    last = bisect_left(bars.times, end)
    result = ResearchPerformance()
    if last - first < 100:
        return result
    seen: set[tuple[str, tuple[int, float]]] = set()
    pending: dict[str, float | int | str] | None = None
    trade: dict[str, float | int | str | bool] | None = None
    entry_fee_rate = 0.001 if series.asset_class == "crypto" else 0.0

    for i in range(first, last):
        if pending is not None and i == int(pending["entry_i"]):
            direction = str(pending["direction"])
            entry = _adverse_fill(
                bars.opens[i], direction, True, bars.symbol
            )
            stop = float(pending["stop"])
            risk = abs(entry - stop)
            if risk > 0:
                sign = 1.0 if direction == "long" else -1.0
                trade = {
                    "direction": direction,
                    "entry_i": i,
                    "entry": entry,
                    "stop": stop,
                    "risk": risk,
                    "partial_target": (
                        entry + sign * risk * float(cfg.partial_at_r)
                        if cfg.partial_at_r is not None
                        else entry
                    ),
                    "runner_target": entry + sign * risk * cfg.rr,
                    "partial_taken": False,
                    "realized_r": -entry_fee_rate * entry / risk,
                }
            pending = None

        if trade is not None:
            direction = str(trade["direction"])
            entry = float(trade["entry"])
            risk = float(trade["risk"])
            stop = float(trade["stop"])
            partial_taken = bool(trade["partial_taken"])
            stop_hit = (
                bars.lows[i] <= stop
                if direction == "long"
                else bars.highs[i] >= stop
            )
            runner_hit = (
                bars.highs[i] >= float(trade["runner_target"])
                if direction == "long"
                else bars.lows[i] <= float(trade["runner_target"])
            )
            partial_hit = (
                bars.highs[i] >= float(trade["partial_target"])
                if direction == "long"
                else bars.lows[i] <= float(trade["partial_target"])
            )
            final_raw: float | None = None
            if stop_hit:
                final_raw = stop
            elif (
                cfg.partial_at_r is not None
                and not partial_taken
                and partial_hit
            ):
                partial_fill = _adverse_fill(
                    float(trade["partial_target"]),
                    direction,
                    False,
                    bars.symbol,
                )
                trade["realized_r"] = float(trade["realized_r"]) + _trade_r(
                    direction=direction,
                    entry=entry,
                    exit_price=partial_fill,
                    risk=risk,
                    weight=cfg.partial_fraction,
                )
                trade["realized_r"] = float(trade["realized_r"]) - (
                    entry_fee_rate
                    * cfg.partial_fraction
                    * partial_fill
                    / risk
                )
                trade["partial_taken"] = True
                trade["stop"] = entry
                partial_taken = True
                if runner_hit:
                    final_raw = float(trade["runner_target"])
            elif runner_hit:
                final_raw = float(trade["runner_target"])
            elif i - int(trade["entry_i"]) >= cfg.max_bars or i == last - 1:
                final_raw = bars.closes[i]

            if final_raw is not None:
                remaining = (
                    1.0 - cfg.partial_fraction if partial_taken else 1.0
                )
                fill = _adverse_fill(
                    final_raw, direction, False, bars.symbol
                )
                outcome = float(trade["realized_r"]) + _trade_r(
                    direction=direction,
                    entry=entry,
                    exit_price=fill,
                    risk=risk,
                    weight=remaining,
                )
                outcome -= entry_fee_rate * remaining * fill / risk
                result.outcomes_r.append(outcome)
                trade = None

        if trade is not None or pending is not None or i >= last - 1:
            continue
        volatility_high = series.volatility_high[i]
        if volatility_high is None:
            continue
        if (cfg.volatility_regime == "high") != volatility_high:
            continue
        direction = _trend_direction(series, i, cfg.trend_strength)
        if direction is None:
            continue
        swing = bars.swing_high[i] if direction == "long" else bars.swing_low[i]
        stop_swing = bars.swing_low[i] if direction == "long" else bars.swing_high[i]
        atr_value = series.atr_values[i]
        if swing is None or stop_swing is None or atr_value is None:
            continue
        anchor = (direction, swing)
        if anchor in seen:
            continue
        close = bars.closes[i]
        broken = close > swing[1] if direction == "long" else close < swing[1]
        if not broken:
            continue
        if series.asset_class == "crypto":
            ratio = bars.vol_ratio[i]
            if ratio is None or ratio < cfg.volume_min:
                continue
        extension = abs(close - swing[1]) / atr_value
        if extension > 2.0:
            continue
        stop = stop_swing[1]
        if (direction == "long" and stop >= close) or (
            direction == "short" and stop <= close
        ):
            continue
        seen.add(anchor)
        pending = {"entry_i": i + 1, "direction": direction, "stop": stop}
    return result


def _crypto_folds(series: AssetSeries) -> list[TimeFold]:
    first_year = max(2018, series.entry.times[0].year)
    return [
        TimeFold(
            code=str(year),
            train_start=datetime(first_year, 1, 1, tzinfo=UTC),
            train_end=datetime(year, 1, 1, tzinfo=UTC),
            test_start=datetime(year, 1, 1, tzinfo=UTC),
            test_end=datetime(year + 1, 1, 1, tzinfo=UTC),
            embargo_bars=80,
        )
        for year in range(max(first_year + 2, 2022), 2027)
    ]


def _forex_folds(series: AssetSeries) -> list[TimeFold]:
    start = series.entry.times[0]
    boundaries = (
        datetime(2025, 7, 1, tzinfo=UTC),
        datetime(2025, 10, 1, tzinfo=UTC),
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 4, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
    )
    now_end = series.entry.times[-1] + timedelta(hours=1)
    folds: list[TimeFold] = []
    for test_start in boundaries:
        test_end = min(test_start + timedelta(days=92), now_end)
        if test_start >= now_end or test_end <= test_start:
            continue
        folds.append(
            TimeFold(
                code=f"{test_start.year}Q{(test_start.month - 1) // 3 + 1}",
                train_start=start,
                train_end=test_start,
                test_start=test_start,
                test_end=test_end,
                embargo_bars=80,
            )
        )
    return folds


def _configs(asset_class: str) -> list[MultiMarketConfig]:
    volume_values = (1.5, 2.0) if asset_class == "crypto" else (0.0,)
    management = (
        (None, 0.0),
        (1.0, 0.5),
        (1.25, 0.5),
    )
    return [
        MultiMarketConfig(
            volatility_regime=values[0],
            trend_strength=values[1],
            volume_min=values[2],
            rr=values[3],
            partial_at_r=values[4][0],
            partial_fraction=values[4][1],
            max_bars=values[5],
        )
        for values in product(
            ("high", "low"),
            ("normal", "strong"),
            volume_values,
            (1.0, 1.5, 2.0, 3.0),
            management,
            (40, 80),
        )
    ]


def _cached_evaluator(series: AssetSeries):
    cache: dict[
        tuple[MultiMarketConfig, datetime, datetime],
        ResearchPerformance,
    ] = {}

    def evaluate(
        config: MultiMarketConfig, start: datetime, end: datetime
    ) -> ResearchPerformance:
        key = (config, start, end)
        if key not in cache:
            cache[key] = simulate(series, config, start, end)
        return cache[key]

    return evaluate


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        all_series = [
            await load_asset_series(session, symbol, "crypto")
            for symbol in CORE_CRYPTO_SYMBOLS
        ] + [
            await load_asset_series(session, symbol, "forex")
            for symbol in CORE_FOREX_SYMBOLS
        ]
    print(
        "Loaded "
        + ", ".join(
            f"{item.entry.symbol}:{len(item.entry.times)}" for item in all_series
        ),
        flush=True,
    )

    for series in all_series:
        folds = (
            _crypto_folds(series)
            if series.asset_class == "crypto"
            else _forex_folds(series)
        )
        configs = _configs(series.asset_class)
        evaluate = _cached_evaluator(series)

        print(f"\n{series.entry.symbol} ({series.asset_class})", flush=True)
        min_trades = 35 if series.asset_class == "crypto" else 20
        for objective in ResearchObjective:
            selections = run_walk_forward(
                folds=folds,
                configs=configs,
                policy=SelectionPolicy(
                    objective=objective,
                    min_trades=min_trades,
                    min_mean_r=0.0,
                    min_profit_factor=1.0,
                    max_drawdown_r=20.0,
                ),
                evaluate=evaluate,
            )
            tests = [
                selection.test
                for selection in selections
                if selection.config is not None
            ]
            total = combine_performance(tests)
            rejected = sum(selection.config is None for selection in selections)
            print(
                f"  {objective.value}: n={total.trades} WR={total.win_rate:.1%} "
                f"mean={total.mean_r:.3f} PF={total.profit_factor:.2f} "
                f"DD={total.max_drawdown_r:.2f}R no_model_folds={rejected}",
                flush=True,
            )
            for selection in selections:
                if selection.config is None:
                    print(
                        f"    {selection.fold.code}: WAIT "
                        f"({selection.rejection_reason})",
                        flush=True,
                    )
                else:
                    print(
                        f"    {selection.fold.code}: {selection.config} "
                        f"test_n={selection.test.trades} "
                        f"WR={selection.test.win_rate:.1%} "
                        f"mean={selection.test.mean_r:.3f}",
                        flush=True,
                    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
