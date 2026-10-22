"""Nested walk-forward comparison of pair-specific strategy families."""

from __future__ import annotations

import asyncio
import time
from bisect import bisect_left
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple

from _multi_market_walkforward import (
    AssetSeries,
    _crypto_folds,
    _forex_folds,
    _trade_r,
    _trend_direction,
    load_asset_series,
)
from private_trading_backtest.walkforward import (
    ResearchObjective,
    ResearchPerformance,
    SelectionPolicy,
    combine_performance,
    evaluate_promotion,
    pair_cost_bps,
    run_walk_forward,
)
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_features.specialist import in_liquid_forex_session
from private_trading_features.types import CandleBar
from private_trading_market_data.universe import (
    CORE_CRYPTO_SYMBOLS,
    CORE_FOREX_SYMBOLS,
)
from private_trading_strategies.multi_market import MarketRegime
from private_trading_strategies.specialist_catalog import specialist_candidates
from private_trading_strategies.specialists import (
    SpecialistAction,
    SpecialistConfig,
    SpecialistContext,
    StrategyFamily,
    evaluate_specialist,
)


def _pair_fill(raw: float, direction: str, entering: bool, symbol: str) -> float:
    multiplier = pair_cost_bps(symbol) / 10_000.0
    adverse_up = (direction == "long") == entering
    return raw * (1.0 + multiplier if adverse_up else 1.0 - multiplier)


def _bars(series: AssetSeries) -> list[CandleBar]:
    source = series.entry
    return [
        CandleBar(
            open_time=source.times[i],
            open=Decimal(str(source.opens[i])),
            high=Decimal(str(source.highs[i])),
            low=Decimal(str(source.lows[i])),
            close=Decimal(str(source.closes[i])),
            volume=Decimal(str(source.volumes[i])),
            is_final=True,
        )
        for i in range(len(source.times))
    ]


class PreparedSeries(NamedTuple):
    series: AssetSeries
    entry: list[CandleBar]
    higher: list[CandleBar]
    regimes: list[MarketRegime | None]
    benchmark: list[CandleBar] | None
    benchmark_by_time: dict[datetime, int]


def _higher_bars(series: AssetSeries) -> list[CandleBar]:
    return [
        CandleBar(
            open_time=series.entry.times[0],
            open=Decimal(str(close)),
            high=Decimal(str(close)),
            low=Decimal(str(close)),
            close=Decimal(str(close)),
            volume=None,
            is_final=True,
        )
        for close in series.htf_closes
    ]


def _regimes(series: AssetSeries) -> list[MarketRegime | None]:
    out: list[MarketRegime | None] = []
    for index, high_vol in enumerate(series.volatility_high):
        if high_vol is None:
            out.append(None)
            continue
        trending = _trend_direction(series, index, "normal") is not None
        if trending:
            out.append(
                MarketRegime.TREND_HIGH_VOL
                if high_vol
                else MarketRegime.TREND_LOW_VOL
            )
        else:
            out.append(
                MarketRegime.RANGE_HIGH_VOL
                if high_vol
                else MarketRegime.RANGE_LOW_VOL
            )
    return out


def simulate(
    prepared: PreparedSeries,
    config: SpecialistConfig,
    start: datetime,
    end: datetime,
) -> ResearchPerformance:
    series = prepared.series
    entry = prepared.entry
    higher = prepared.higher
    regimes = prepared.regimes
    benchmark_bars = prepared.benchmark
    benchmark_by_time = prepared.benchmark_by_time
    first = bisect_left(series.entry.times, start)
    last = bisect_left(series.entry.times, end)
    result = ResearchPerformance()
    if last - first < 100:
        return result

    pending: dict[str, Decimal | int | str] | None = None
    trade: dict[str, Decimal | int | str | bool] | None = None
    seen: set[tuple[str, str, Decimal]] = set()
    fee_rate = Decimal("0.001") if series.asset_class == "crypto" else Decimal("0")

    for index in range(first, last):
        bar = entry[index]
        if pending is not None and index == int(pending["entry_i"]):
            direction = str(pending["direction"])
            raw_entry = float(bar.open)
            filled = Decimal(
                str(_pair_fill(raw_entry, direction, True, series.entry.symbol))
            )
            stop = Decimal(str(pending["stop"]))
            risk = abs(filled - stop)
            if risk > 0:
                sign = Decimal("1") if direction == "long" else Decimal("-1")
                trade = {
                    "direction": direction,
                    "entry_i": index,
                    "entry": filled,
                    "stop": stop,
                    "risk": risk,
                    "target": filled + sign * risk * config.rr,
                    "partial_target": (
                        filled + sign * risk * config.partial_at_r
                        if config.partial_at_r is not None
                        else filled
                    ),
                    "partial_taken": False,
                    "realized_r": -(fee_rate * filled / risk),
                }
            pending = None

        if trade is not None:
            direction = str(trade["direction"])
            filled = Decimal(str(trade["entry"]))
            risk = Decimal(str(trade["risk"]))
            stop = Decimal(str(trade["stop"]))
            partial_taken = bool(trade["partial_taken"])
            stop_hit = bar.low <= stop if direction == "long" else bar.high >= stop
            target = Decimal(str(trade["target"]))
            runner_hit = bar.high >= target if direction == "long" else bar.low <= target
            partial_target = Decimal(str(trade["partial_target"]))
            partial_hit = (
                bar.high >= partial_target
                if direction == "long"
                else bar.low <= partial_target
            )
            final_raw: Decimal | None = None
            if stop_hit:
                final_raw = stop
            elif (
                config.partial_at_r is not None
                and not partial_taken
                and partial_hit
            ):
                partial_fill = Decimal(
                    str(
                        _pair_fill(
                            float(partial_target),
                            direction,
                            False,
                            series.entry.symbol,
                        )
                    )
                )
                trade["realized_r"] = Decimal(str(trade["realized_r"])) + Decimal(
                    str(
                        _trade_r(
                            direction=direction,
                            entry=float(filled),
                            exit_price=float(partial_fill),
                            risk=float(risk),
                            weight=float(config.partial_fraction),
                        )
                    )
                )
                trade["realized_r"] = Decimal(str(trade["realized_r"])) - (
                    fee_rate * config.partial_fraction * partial_fill / risk
                )
                trade["partial_taken"] = True
                trade["stop"] = filled
                partial_taken = True
                if runner_hit:
                    final_raw = target
            elif runner_hit:
                final_raw = target
            elif index - int(trade["entry_i"]) >= config.max_bars or index == last - 1:
                final_raw = bar.close

            if final_raw is not None:
                remaining = (
                    Decimal("1") - config.partial_fraction
                    if partial_taken
                    else Decimal("1")
                )
                exit_fill = Decimal(
                    str(
                        _pair_fill(
                            float(final_raw),
                            direction,
                            False,
                            series.entry.symbol,
                        )
                    )
                )
                gross_r = Decimal(
                    str(
                        _trade_r(
                            direction=direction,
                            entry=float(filled),
                            exit_price=float(exit_fill),
                            risk=float(risk),
                            weight=float(remaining),
                        )
                    )
                )
                outcome = Decimal(str(trade["realized_r"])) + gross_r
                outcome -= fee_rate * remaining * exit_fill / risk
                result.outcomes_r.append(float(outcome))
                trade = None

        if trade is not None or pending is not None or index >= last - 1:
            continue
        regime = regimes[index]
        htf_index = series.htf_index[index]
        if regime is None or htf_index is None or index < 120 or htf_index < 60:
            continue
        if regime not in config.allowed_regimes:
            continue
        if (
            config.family
            in {StrategyFamily.SESSION_BREAKOUT, StrategyFamily.SESSION_PULLBACK}
            and not in_liquid_forex_session(bar.open_time.hour)
        ):
            continue
        own_window = entry[index - 119 : index + 1]
        htf_window = higher[htf_index - 59 : htf_index + 1]
        benchmark_window: list[CandleBar] | None = None
        if benchmark_bars is not None:
            benchmark_index = benchmark_by_time.get(bar.open_time)
            if benchmark_index is None or benchmark_index < 119:
                continue
            benchmark_window = benchmark_bars[
                benchmark_index - 119 : benchmark_index + 1
            ]
        signal = evaluate_specialist(
            config,
            SpecialistContext(
                entry_bars=own_window,
                higher_timeframe_bars=htf_window,
                regime=regime,
                benchmark_bars=benchmark_window,
            ),
        )
        if (
            signal.action != SpecialistAction.ENTER
            or signal.direction is None
            or signal.entry_reference is None
            or signal.stop_price is None
        ):
            continue
        anchor = (config.family.value, signal.direction, signal.entry_reference)
        if anchor in seen:
            continue
        seen.add(anchor)
        pending = {
            "entry_i": index + 1,
            "direction": signal.direction,
            "stop": signal.stop_price,
        }
    return result


def _prepare(
    series: AssetSeries,
    benchmark: AssetSeries | None,
) -> PreparedSeries:
    benchmark_bars = _bars(benchmark) if benchmark is not None else None
    return PreparedSeries(
        series=series,
        entry=_bars(series),
        higher=_higher_bars(series),
        regimes=_regimes(series),
        benchmark=benchmark_bars,
        benchmark_by_time=(
            {bar.open_time: index for index, bar in enumerate(benchmark_bars)}
            if benchmark_bars is not None
            else {}
        ),
    )


def _cached_evaluator(prepared: PreparedSeries):
    cache: dict[
        tuple[SpecialistConfig, datetime, datetime],
        ResearchPerformance,
    ] = {}

    def evaluate(
        config: SpecialistConfig,
        start: datetime,
        end: datetime,
    ) -> ResearchPerformance:
        key = (config, start, end)
        if key not in cache:
            started = time.perf_counter()
            cache[key] = simulate(prepared, config, start, end)
            print(
                f"    eval {config.code} {start.date()}->{end.date()} "
                f"n={cache[key].trades} {time.perf_counter() - started:.1f}s",
                flush=True,
            )
        return cache[key]

    return evaluate


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        series_by_symbol = {
            symbol: await load_asset_series(session, symbol, "crypto")
            for symbol in CORE_CRYPTO_SYMBOLS
        }
        series_by_symbol.update(
            {
                symbol: await load_asset_series(session, symbol, "forex")
                for symbol in CORE_FOREX_SYMBOLS
            }
        )
    benchmark = series_by_symbol["BTC/USDT"]
    for symbol, series in series_by_symbol.items():
        configs = list(specialist_candidates(symbol))
        folds = (
            _crypto_folds(series)
            if series.asset_class == "crypto"
            else _forex_folds(series)
        )
        evaluate = _cached_evaluator(
            _prepare(series, benchmark if symbol == "ETH/USDT" else None)
        )

        print(f"\n{symbol} specialist families={len(configs)}", flush=True)
        for objective in ResearchObjective:
            selections = run_walk_forward(
                folds=folds,
                configs=configs,
                policy=SelectionPolicy(
                    objective=objective,
                    min_trades=30 if series.asset_class == "crypto" else 20,
                    min_mean_r=0.0,
                    min_profit_factor=1.0,
                    max_drawdown_r=20.0,
                ),
                evaluate=evaluate,
            )
            tested = [
                selection.test
                for selection in selections
                if selection.config is not None
            ]
            total = combine_performance(tested)
            promotion = evaluate_promotion(
                tested,
                min_total_trades=80 if series.asset_class == "crypto" else 50,
                min_mean_r=0.05,
                min_profit_factor=1.1,
                max_drawdown_r=20.0,
                min_positive_period_fraction=0.6,
                incumbent_mean_r=(
                    0.215
                    if symbol == "SOL/USDT"
                    and objective == ResearchObjective.PROFIT
                    else None
                ),
                incumbent_win_rate=(
                    0.589
                    if symbol == "SOL/USDT"
                    and objective == ResearchObjective.WIN_RATE
                    else None
                ),
            )
            print(
                f"  {objective.value}: n={total.trades} WR={total.win_rate:.1%} "
                f"mean={total.mean_r:.3f} PF={total.profit_factor:.2f} "
                f"DD={total.max_drawdown_r:.2f}R "
                f"PROMOTE={promotion.approved} reasons={list(promotion.reasons)}",
                flush=True,
            )
            for selection in selections:
                if selection.config is None:
                    print(f"    {selection.fold.code}: WAIT no_model", flush=True)
                else:
                    print(
                        f"    {selection.fold.code}: "
                        f"{selection.config.family.value}/{selection.config.code} "
                        f"n={selection.test.trades} "
                        f"WR={selection.test.win_rate:.1%} "
                        f"mean={selection.test.mean_r:.3f}",
                        flush=True,
                    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
