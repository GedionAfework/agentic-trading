"""Honest nested walk-forward for DOGE (owner 2-week coin test).

DOGE was not in the spent specialist/core search set. BTC/ETH stay WAIT from
prior rejects; SOL keeps V1 paper soak. This script never writes the registry.
"""

from __future__ import annotations

import asyncio

from _multi_market_walkforward import (
    _cached_evaluator,
    _configs,
    _crypto_folds,
    load_asset_series,
)
from private_trading_backtest.walkforward import (
    ResearchObjective,
    SelectionPolicy,
    combine_performance,
    evaluate_promotion,
    run_walk_forward,
)
from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_market_data.catalog import ensure_binance_catalog
from private_trading_market_data.ingest import sync_instrument_candles
from private_trading_market_data.providers import BinanceSpotProvider

SYMBOL = "DOGE/USDT"


async def _ensure_doge_candles(session) -> None:
    await ensure_binance_catalog(session)
    await session.commit()
    provider = BinanceSpotProvider(timeout_seconds=60.0)
    try:
        for timeframe in ("1h", "4h", "1d"):
            try:
                out = await sync_instrument_candles(
                    session,
                    provider,
                    canonical_symbol=SYMBOL,
                    timeframe=timeframe,
                    limit=1000,
                )
                print(
                    f"sync {out.instrument_symbol} {out.timeframe} "
                    f"upserted={out.upserted}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 — use stored bars if sync flakes
                await session.rollback()
                print(f"sync skip {timeframe}: {type(exc).__name__}: {exc}", flush=True)
    finally:
        await provider.aclose()


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await _ensure_doge_candles(session)
        series = await load_asset_series(session, SYMBOL, "crypto")
    print(f"Loaded {SYMBOL} bars={len(series.entry.times)}", flush=True)

    evaluate = _cached_evaluator(series)
    selections = run_walk_forward(
        folds=_crypto_folds(series),
        configs=_configs("crypto"),
        policy=SelectionPolicy(
            ResearchObjective.PROFIT,
            min_trades=35,
            min_mean_r=0.0,
            min_profit_factor=1.0,
            max_drawdown_r=20.0,
        ),
        evaluate=evaluate,
    )
    tests = [row.test for row in selections if row.config is not None]
    combined = combine_performance(tests)
    decision = evaluate_promotion(
        tests,
        min_total_trades=80,
        min_mean_r=0.05,
        min_profit_factor=1.1,
        max_drawdown_r=20.0,
        min_positive_period_fraction=0.6,
    )

    print("\nPer-fold:", flush=True)
    for row in selections:
        if row.config is None:
            print(f"  {row.fold.code}: WAIT ({row.rejection_reason})", flush=True)
        else:
            cfg = row.config
            print(
                f"  {row.fold.code}: vol={cfg.volatility_regime} "
                f"trend={cfg.trend_strength} vol_min={cfg.volume_min} "
                f"rr={cfg.rr} n={row.test.trades} "
                f"WR={row.test.win_rate:.1%} mean={row.test.mean_r:+.3f}",
                flush=True,
            )

    print(
        f"\nCombined n={combined.trades} WR={combined.win_rate:.1%} "
        f"mean={combined.mean_r:+.3f} PF={combined.profit_factor:.2f} "
        f"DD={combined.max_drawdown_r:.2f}R "
        f"positive={decision.positive_period_fraction:.0%}",
        flush=True,
    )
    print(
        f"decision={'PASS' if decision.approved else 'REJECT'} "
        f"reasons={decision.reasons or ('none',)}",
        flush=True,
    )
    print("registry: unchanged (fail-closed)", flush=True)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
