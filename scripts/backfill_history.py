#!/usr/bin/env python3
"""Backfill max free crypto (Binance) + forex (Yahoo) history into Postgres.

Default TFs skip 1m/5m (huge). Use --fast to include them.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from private_trading_db.session import dispose_engine, get_session_factory
from private_trading_market_data.backfill import run_max_free_backfill


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Also backfill 1m/5m crypto (very large / slow)",
    )
    parser.add_argument(
        "--crypto-only",
        action="store_true",
        help="Skip forex",
    )
    parser.add_argument(
        "--forex-only",
        action="store_true",
        help="Skip crypto",
    )
    args = parser.parse_args(argv)

    crypto_tfs = ("15m", "1h", "4h", "1d")
    if args.fast:
        crypto_tfs = ("1m", "5m") + crypto_tfs
    forex_tfs = ("1h", "1d")

    factory = get_session_factory()
    async with factory() as session:
        results = await run_max_free_backfill(
            session,
            crypto_timeframes=() if args.forex_only else crypto_tfs,
            forex_timeframes=() if args.crypto_only else forex_tfs,
            crypto_symbols=() if args.forex_only else None,
            forex_symbols=() if args.crypto_only else None,
        )
    await dispose_engine()

    print(json.dumps(results, indent=2))
    errors = [r for r in results if r.get("error")]
    total = sum(int(r.get("upserted") or 0) for r in results)
    print(
        f"\nbackfill_done upserted={total} series={len(results)} errors={len(errors)}",
        flush=True,
    )
    return 1 if errors and total == 0 else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
