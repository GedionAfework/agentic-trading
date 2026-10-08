"""Select 1h strategy settings on old data, then score once on untouched recent data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import product

from private_trading_db.models.market import Candle, Instrument
from private_trading_db.session import dispose_engine, get_session_factory
from sqlalchemy import select

SYMBOLS = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT")
TEST_START = datetime(2024, 1, 1, tzinfo=UTC)
RADIUS = 2


@dataclass(slots=True)
class Series:
    symbol: str
    times: list[datetime]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    ema12: list[float | None]
    ema21: list[float | None]
    ema50: list[float | None]
    swing_high: list[tuple[int, float] | None]
    swing_low: list[tuple[int, float] | None]
    vol_ratio: list[float | None]


@dataclass(slots=True, frozen=True)
class Config:
    trend: str
    vol_threshold: float
    rr: float
    max_bars: int


@dataclass(slots=True)
class Metrics:
    trades: int = 0
    wins: int = 0
    r_sum: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def mean_r(self) -> float:
        return self.r_sum / self.trades if self.trades else 0.0

    def add(self, r_value: float) -> None:
        self.trades += 1
        self.wins += int(r_value > 0)
        self.r_sum += r_value


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    value = sum(values[:period]) / period
    out[period - 1] = value
    k = 2.0 / (period + 1)
    for i in range(period, len(values)):
        value = values[i] * k + value * (1.0 - k)
        out[i] = value
    return out


def prior_swings(
    highs: list[float], lows: list[float]
) -> tuple[list[tuple[int, float] | None], list[tuple[int, float] | None]]:
    n = len(highs)
    piv_hi: dict[int, float] = {}
    piv_lo: dict[int, float] = {}
    for j in range(RADIUS, n - RADIUS):
        hi_window = highs[j - RADIUS : j + RADIUS + 1]
        lo_window = lows[j - RADIUS : j + RADIUS + 1]
        if highs[j] == max(hi_window) and hi_window.count(highs[j]) == 1:
            piv_hi[j] = highs[j]
        if lows[j] == min(lo_window) and lo_window.count(lows[j]) == 1:
            piv_lo[j] = lows[j]
    last_hi: tuple[int, float] | None = None
    last_lo: tuple[int, float] | None = None
    out_hi: list[tuple[int, float] | None] = [None] * n
    out_lo: list[tuple[int, float] | None] = [None] * n
    for i in range(n):
        confirmed = i - RADIUS
        if confirmed in piv_hi:
            last_hi = (confirmed, piv_hi[confirmed])
        if confirmed in piv_lo:
            last_lo = (confirmed, piv_lo[confirmed])
        out_hi[i] = last_hi
        out_lo[i] = last_lo
    return out_hi, out_lo


def volume_ratio(values: list[float], period: int = 20) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1 and running > 0:
            out[i] = value / (running / period)
    return out


def trend_passes(series: Series, i: int, mode: str) -> bool:
    c = series.closes[i]
    e12, e21, e50 = series.ema12[i], series.ema21[i], series.ema50[i]
    if e50 is None:
        return False
    if mode == "close50":
        return c > e50
    if mode == "stack":
        return e12 is not None and e21 is not None and c > e12 > e21 > e50
    if mode == "close50_slope":
        prior = series.ema50[i - 10] if i >= 10 else None
        return prior is not None and c > e50 > prior
    if mode == "stack_slope":
        prior = series.ema50[i - 10] if i >= 10 else None
        return (
            prior is not None
            and e12 is not None
            and e21 is not None
            and c > e12 > e21 > e50 > prior
        )
    raise ValueError(mode)


def adverse_entry(raw: float) -> float:
    # 5 bps slippage + 1 bp half-spread. Fee is charged separately.
    return raw * (1.0 + 0.0006)


def adverse_exit(raw: float) -> float:
    return raw * (1.0 - 0.0006)


def simulate(series: Series, cfg: Config, *, test: bool) -> Metrics:
    metrics = Metrics()
    seen: set[tuple[int, float]] = set()
    open_trade: dict[str, float | int] | None = None
    pending: dict[str, float | int] | None = None
    for i in range(len(series.times)):
        is_test = series.times[i] >= TEST_START
        if open_trade is not None:
            stop = float(open_trade["stop"])
            target = float(open_trade["target"])
            hit_stop = series.lows[i] <= stop
            hit_target = series.highs[i] >= target
            exit_raw: float | None = None
            if hit_stop:
                exit_raw = stop
            elif hit_target:
                exit_raw = target
            elif i - int(open_trade["entry_i"]) >= cfg.max_bars:
                exit_raw = series.closes[i]
            if exit_raw is not None:
                entry = float(open_trade["entry"])
                risk = entry - stop
                # Same conservative cost convention used by the engine.
                exit_fill = adverse_exit(exit_raw)
                cogs = entry * 0.001 + exit_fill * 0.001
                pnl_r = (exit_fill - entry - cogs) / risk if risk > 0 else 0.0
                if bool(open_trade["test"]) == test:
                    metrics.add(pnl_r)
                open_trade = None
        if pending is not None and open_trade is None and i == int(pending["entry_i"]):
            open_trade = {
                **pending,
                "entry": adverse_entry(series.opens[i]),
                "test": is_test,
            }
            pending = None
        if open_trade is not None or pending is not None or i >= len(series.times) - 1:
            continue
        if is_test != test:
            continue
        swing_hi = series.swing_high[i]
        swing_lo = series.swing_low[i]
        vr = series.vol_ratio[i]
        if swing_hi is None or swing_lo is None or vr is None:
            continue
        anchor = swing_hi
        if anchor in seen:
            continue
        if series.closes[i] <= swing_hi[1] or vr < cfg.vol_threshold:
            continue
        if not trend_passes(series, i, cfg.trend):
            continue
        stop = swing_lo[1]
        signal_close = series.closes[i]
        risk = signal_close - stop
        if risk <= 0:
            continue
        seen.add(anchor)
        pending = {
            "entry_i": i + 1,
            "stop": stop,
            "target": signal_close + risk * cfg.rr,
        }
    return metrics


async def load_series(session, symbol: str) -> Series:
    instrument = (
        await session.execute(select(Instrument).where(Instrument.canonical_symbol == symbol))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Candle)
            .where(
                Candle.instrument_id == instrument.id,
                Candle.timeframe == "1h",
                Candle.is_final.is_(True),
            )
            .order_by(Candle.open_time)
        )
    ).scalars().all()
    times = [r.open_time for r in rows]
    opens = [float(r.open) for r in rows]
    highs = [float(r.high) for r in rows]
    lows = [float(r.low) for r in rows]
    closes = [float(r.close) for r in rows]
    volumes = [float(r.volume or 0) for r in rows]
    swing_high, swing_low = prior_swings(highs, lows)
    return Series(
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


def aggregate(series: list[Series], cfg: Config, *, test: bool) -> Metrics:
    total = Metrics()
    for item in series:
        result = simulate(item, cfg, test=test)
        total.trades += result.trades
        total.wins += result.wins
        total.r_sum += result.r_sum
    return total


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        series = [await load_series(session, symbol) for symbol in SYMBOLS]
    print("Loaded " + ", ".join(f"{s.symbol}={len(s.times)}" for s in series), flush=True)

    configs = [
        Config(*values)
        for values in product(
            ("close50", "stack", "close50_slope", "stack_slope"),
            (1.2, 1.5, 1.8, 2.0),
            (1.5, 2.0, 2.5, 3.0),
            (20, 40, 80),
        )
    ]
    ranked: list[tuple[float, Config, Metrics]] = []
    for cfg in configs:
        train = aggregate(series, cfg, test=False)
        if train.trades < 100:
            continue
        # Prefer edge with enough observations; no test data participates.
        score = train.mean_r - 1.0 / (train.trades**0.5)
        ranked.append((score, cfg, train))
    ranked.sort(key=lambda row: row[0], reverse=True)

    print("\nTop five selected only on pre-2024 data:", flush=True)
    for _score, cfg, train in ranked[:5]:
        print(
            f"{cfg} train n={train.trades} WR={train.win_rate:.1%} mean_R={train.mean_r:.3f}",
            flush=True,
        )

    winner = ranked[0][1]
    baseline = Config("close50", 1.5, 2.0, 40)
    print("\nUntouched 2024+ test (not used for selection):", flush=True)
    for label, cfg in (("baseline", baseline), ("winner", winner)):
        result = aggregate(series, cfg, test=True)
        print(
            f"{label} {cfg} test n={result.trades} "
            f"WR={result.win_rate:.1%} mean_R={result.mean_r:.3f}",
            flush=True,
        )
        for item in series:
            one = simulate(item, cfg, test=True)
            print(
                f"  {item.symbol} n={one.trades} WR={one.win_rate:.1%} mean_R={one.mean_r:.3f}",
                flush=True,
            )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
