"""BTC regime split for the frozen 4h->1h BOS/volume model on BTC/ETH/SOL/DOGE.

INFORMATIONAL ONLY. 2022-2026 is spent for SOL V1 (and BTC regime agreement
was already in V1's search grid, where walk-forward chose btc_filter=False).
No parameters are searched here: one pre-declared BTC rule (4h EMA 12>21>50
with rising EMA50, completed candles) and the frozen V1 config per coin.

For each coin and year: all trades vs trades taken while BTC was risk-on vs
risk-off. Use this to decide whether a BTC regime tag is worth *shadowing* on
new paper trades, never to add a live filter.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _live_sol_winrate import build_mtf, fetch_all  # noqa: E402
from _mtf_oos_search import htf_passes  # noqa: E402
from _oos_strategy_search import Metrics  # noqa: E402
from _walkforward_challenger import ChallengerConfig, atr, simulate_year  # noqa: E402
from private_trading_market_data.providers.binance import BinanceSpotProvider  # noqa: E402

BTC_RULE = "stack_slope"
COINS = (("BTCUSDT", "BTC/USDT"), ("ETHUSDT", "ETH/USDT"), ("SOLUSDT", "SOL/USDT"),
         ("DOGEUSDT", "DOGE/USDT"))
YEARS = (2022, 2023, 2024, 2025, 2026)

# Frozen V1 config (also DOGE V1: 4h trend, 1h BOS, vol>=2, 3R, 80 bars).
CFG_ALL = ChallengerConfig(
    htf_trend="stack_slope", vol_threshold=2.0, rr=3.0, max_bars=80,
    max_extension_atr=2.0, btc_filter=False, breakeven_at_1r=False,
)
CFG_FILTER = ChallengerConfig(
    htf_trend="stack_slope", vol_threshold=2.0, rr=3.0, max_bars=80,
    max_extension_atr=2.0, btc_filter=True, breakeven_at_1r=False,
)


def fmt(m: Metrics) -> str:
    if not m.trades:
        return f"{0:>4}  {'—':>6}  {'—':>7}"
    return f"{m.trades:>4}  {100 * m.win_rate:>5.1f}%  {m.mean_r:>+7.3f}"


def add(total: Metrics, part: Metrics) -> None:
    total.trades += part.trades
    total.wins += part.wins
    total.r_sum += part.r_sum


async def main() -> None:
    start = datetime(2022, 1, 1, tzinfo=UTC)
    provider = BinanceSpotProvider(timeout_seconds=60.0)
    series = {}
    try:
        for pair, symbol in COINS:
            print(f"fetching {pair} 1h+4h…", flush=True)
            one = await fetch_all(provider, symbol=pair, timeframe="1h", start=start)
            four = await fetch_all(provider, symbol=pair, timeframe="4h", start=start)
            series[symbol] = build_mtf(one, four, symbol=symbol)
            print(f"  {symbol}: 1h={len(one)} 4h={len(four)} "
                  f"{one[0].open_time:%Y-%m-%d}..{one[-1].open_time:%Y-%m-%d}", flush=True)
    finally:
        await provider.aclose()

    btc = series["BTC/USDT"]
    risk_on = {t: htf_passes(btc, i, BTC_RULE) for i, t in enumerate(btc.entry.times)}
    risk_off = {t: not v for t, v in risk_on.items()}
    on_share = sum(risk_on.values()) / max(1, len(risk_on))
    print(f"\nBTC risk-on share of 1h bars: {100 * on_share:.1f}%  (rule: BTC 4h {BTC_RULE})")
    print("Columns: trades  win%  meanR   (after 10 bps/side fees + adverse fills)\n")

    for _pair, symbol in COINS:
        s = series[symbol]
        atr_values = atr(s.entry.highs, s.entry.lows, s.entry.closes)
        print(f"== {symbol} ==")
        print(f"{'year':<6}{'ALL':>20}{'BTC risk-on':>22}{'BTC risk-off':>22}")
        tot_all, tot_on, tot_off = Metrics(), Metrics(), Metrics()
        for year in YEARS:
            m_all = simulate_year(s, CFG_ALL, year=year, atr_values=atr_values,
                                  btc_regime=risk_on)
            add(tot_all, m_all)
            if symbol == "BTC/USDT":
                # BTC's own 4h trend is already required by the model.
                print(f"{year:<6}{fmt(m_all):>20}{'(own trend)':>22}{'':>22}")
                continue
            m_on = simulate_year(s, CFG_FILTER, year=year, atr_values=atr_values,
                                 btc_regime=risk_on)
            m_off = simulate_year(s, CFG_FILTER, year=year, atr_values=atr_values,
                                  btc_regime=risk_off)
            add(tot_on, m_on)
            add(tot_off, m_off)
            print(f"{year:<6}{fmt(m_all):>20}{fmt(m_on):>22}{fmt(m_off):>22}")
        if symbol == "BTC/USDT":
            print(f"{'total':<6}{fmt(tot_all):>20}\n")
        else:
            print(f"{'total':<6}{fmt(tot_all):>20}{fmt(tot_on):>22}{fmt(tot_off):>22}\n")


if __name__ == "__main__":
    asyncio.run(main())
