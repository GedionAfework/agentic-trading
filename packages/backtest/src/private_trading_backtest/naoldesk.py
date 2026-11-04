"""NaolDesk breakout/spring simulator — the single source of truth.

Frozen rules: docs/strategy/STEP6_HYPOTHESIS_NAOLDESK.md (+ _V2.md for the
4h structure exit). Used by the research script AND the forward paper
challenger ledger, so research and live evaluation cannot drift apart.
Do not change any constant: a change is a new, pre-registered version.
"""

from __future__ import annotations

from collections import Counter  # noqa: F401  (kept for script parity)
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

SCORE_START = datetime(2022, 1, 1, tzinfo=UTC)

# --- frozen constants ------------------------------------------------------
PIVOT = 3
VOL_MA = 20
BOS_VOL_MULT = 2.0
SPRING_VOL_MULT = 1.5
STOP_ATR_BUFFER = 0.5
RANGE_4H_BARS = 30
RANGE_MAX_ATR4H = 6.0
RECOVERY_WINDOW = 3
TP1_R = 1.0
TP1_FRACTION = 1.0 / 3.0
CLIMAX_VOL_MULT = 2.0
CLIMAX_RANGE_ATR = 0.6
MAX_BARS = 720
FEE = 0.001
DAILY_EMA = 50
DAILY_SLOPE_LOOKBACK = 10


# --- research helpers, copied verbatim (fills, EMA, ATR) -------------------
def adverse_entry(raw: float) -> float:
    # 5 bps slippage + 1 bp half-spread. Fee is charged separately.
    return raw * (1.0 + 0.0006)


def adverse_exit(raw: float) -> float:
    return raw * (1.0 - 0.0006)


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


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14):
    out: list[float | None] = [None] * len(closes)
    trs: list[float] = []
    running = 0.0
    for i in range(len(closes)):
        prev = closes[i - 1] if i else None
        tr = highs[i] - lows[i]
        if prev is not None:
            tr = max(tr, abs(highs[i] - prev), abs(lows[i] - prev))
        trs.append(tr)
        running += tr
        if i >= period:
            running -= trs[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


@dataclass
class Bars:
    t: list[datetime]
    o: list[float]
    h: list[float]
    l: list[float]  # noqa: E741
    c: list[float]
    v: list[float]


def to_bars(rows) -> Bars:
    rows = sorted(rows, key=lambda r: r.open_time)
    norm = [r.open_time if r.open_time.tzinfo else r.open_time.replace(tzinfo=UTC) for r in rows]
    return Bars(norm, [float(r.open) for r in rows], [float(r.high) for r in rows],
                [float(r.low) for r in rows], [float(r.close) for r in rows],
                [float(r.volume or 0) for r in rows])


@dataclass
class Trade:
    coin: str
    setup: str
    entry_time: datetime
    exit_time: datetime
    r: float
    reason: str
    tp1: bool


@dataclass
class Prepared:
    b: Bars
    atr1h: list
    volma: list
    swing_high: list  # latest confirmed swing high (price, pivot index) known at close of i
    swing_low: list
    daily_down: list  # bool per 1h bar, as of its close
    h4_last: list  # index of last 4h candle completed by the 1h bar's open
    atr4h: list
    b4: Bars
    # v2: index of the 4h candle that completes at the close of 1h bar i (else -1)
    h4_done_at: list
    swing_low_4h: list  # latest confirmed 4h swing low known at close of 4h candle q


def prepare(b: Bars, b4: Bars, bd: Bars) -> Prepared:
    n = len(b.t)
    atr1h = atr(b.h, b.l, b.c)
    volma: list[float | None] = [None] * n
    run = 0.0
    for i in range(n):
        if i >= VOL_MA:
            volma[i] = run / VOL_MA
            run -= b.v[i - VOL_MA]
        run += b.v[i]
    # confirmed pivots: pivot j known at close of j + PIVOT
    sh: list = [None] * n
    sl: list = [None] * n
    cur_h = cur_l = None
    for i in range(n):
        j = i - PIVOT
        if j >= PIVOT:
            win_h = b.h[j - PIVOT:j] + b.h[j + 1:j + PIVOT + 1]
            win_l = b.l[j - PIVOT:j] + b.l[j + 1:j + PIVOT + 1]
            if b.h[j] > max(win_h):
                cur_h = (b.h[j], j)
            if b.l[j] < min(win_l):
                cur_l = (b.l[j], j)
        sh[i], sl[i] = cur_h, cur_l
    # daily downtrend as of each 1h close
    d_ema = ema(bd.c, DAILY_EMA)
    daily_down = [False] * n
    k = -1
    for i in range(n):
        close_time = b.t[i] + timedelta(hours=1)
        while k + 1 < len(bd.t) and bd.t[k + 1] + timedelta(days=1) <= close_time:
            k += 1
        if k >= DAILY_SLOPE_LOOKBACK and d_ema[k] is not None and d_ema[k - DAILY_SLOPE_LOOKBACK]:
            daily_down[i] = bd.c[k] < d_ema[k] and d_ema[k] < d_ema[k - DAILY_SLOPE_LOOKBACK]
    # last 4h candle completed before each 1h candle opens
    h4_last = [-1] * n
    k = -1
    for i in range(n):
        while k + 1 < len(b4.t) and b4.t[k + 1] + timedelta(hours=4) <= b.t[i]:
            k += 1
        h4_last[i] = k
    t4_index = {t: q for q, t in enumerate(b4.t)}
    h4_done_at = [t4_index.get(b.t[i] + timedelta(hours=1) - timedelta(hours=4), -1)
                  for i in range(n)]
    sl4: list = [None] * len(b4.t)
    cur = None
    for q in range(len(b4.t)):
        j = q - PIVOT
        if j >= PIVOT and b4.l[j] < min(b4.l[j - PIVOT:j] + b4.l[j + 1:j + PIVOT + 1]):
            cur = (b4.l[j], j)
        sl4[q] = cur
    return Prepared(b, atr1h, volma, sh, sl, daily_down, h4_last,
                    atr(b4.h, b4.l, b4.c), b4, h4_done_at, sl4)


def session_ok(t: datetime) -> bool:
    return t.weekday() < 5 and t.hour not in (22, 23)


@dataclass
class Position:
    entry: float
    stop: float
    risk: float
    entry_k: int
    size: float = 1.0
    gross: float = 0.0
    fees: float = 0.0
    tp1: bool = False


def simulate(
    coin: str,
    p: Prepared,
    setup: str,
    exit_tf: str = "1h",
    *,
    score_start: datetime = SCORE_START,
    close_at_end: bool = True,
    open_out: list | None = None,
) -> list[Trade]:
    b = p.b
    n = len(b.t)
    start = next((i for i, t in enumerate(b.t) if t >= score_start), n)
    trades: list[Trade] = []
    pos: Position | None = None
    pending_entry: float | None = None  # stop price for entry at next open
    pending_exit: str | None = None
    used_swing_highs: set[int] = set()
    used_range_lows: set[float] = set()
    sweep: dict | None = None

    def close(k: int, fill_raw: float, reason: str, at_close: bool = False) -> None:
        nonlocal pos
        assert pos is not None
        fill = adverse_exit(fill_raw)
        pos.gross += pos.size * (fill - pos.entry)
        pos.fees += pos.size * fill * FEE
        r = (pos.gross - pos.fees) / pos.risk
        trades.append(Trade(coin, setup, b.t[pos.entry_k], b.t[k], r, reason, pos.tp1))
        pos = None

    for k in range(start, n):
        # 1) entry at this open
        if pending_entry is not None and pos is None:
            entry = adverse_entry(b.o[k])
            risk = entry - pending_entry
            if risk > 0:
                pos = Position(entry=entry, stop=pending_entry, risk=risk, entry_k=k)
                pos.fees = entry * FEE
        pending_entry = None
        # 2) exit decided at previous close
        if pending_exit is not None and pos is not None:
            close(k, b.o[k], pending_exit)
        pending_exit = None
        # 3) intrabar stop / TP1, then close-based exits
        if pos is not None:
            if b.l[k] <= pos.stop:
                close(k, min(b.o[k], pos.stop), "breakeven" if pos.tp1 else "stop")
            elif not pos.tp1 and b.h[k] >= pos.entry + TP1_R * pos.risk:
                fill = adverse_exit(pos.entry + TP1_R * pos.risk)
                pos.gross += TP1_FRACTION * (fill - pos.entry)
                pos.fees += TP1_FRACTION * fill * FEE
                pos.size -= TP1_FRACTION
                pos.tp1 = True
                pos.stop = pos.entry
        if pos is not None:
            ma = p.volma[k]
            a = p.atr1h[k]
            if _structure_break(p, k, exit_tf):
                pending_exit = "structure"
            elif (b.c[k] > pos.entry and ma and a and b.v[k] >= CLIMAX_VOL_MULT * ma
                  and (b.h[k] - b.l[k]) < CLIMAX_RANGE_ATR * a):
                pending_exit = "climax"
            elif k - pos.entry_k >= MAX_BARS:
                close(k, b.c[k], "time_cap")
        # 4) new signal on this close (flat, nothing pending)
        if pos is not None or pending_exit is not None or k + 1 >= n:
            continue
        if p.daily_down[k] or not session_ok(b.t[k + 1]):
            # Spring sweeps still need tracking even when we can't enter now.
            if setup == "B":
                sweep = _track_sweep(p, k, sweep, used_range_lows)
            continue
        ma, a = p.volma[k], p.atr1h[k]
        if ma is None or a is None:
            continue
        if setup == "A":
            sw = p.swing_high[k]
            if (sw is not None and sw[1] not in used_swing_highs
                    and b.c[k] > sw[0] >= b.c[k - 1] and b.c[k] > b.o[k]
                    and b.v[k] >= BOS_VOL_MULT * ma):
                used_swing_highs.add(sw[1])
                pending_entry = b.l[k] - STOP_ATR_BUFFER * a
        else:
            sweep = _track_sweep(p, k, sweep, used_range_lows)
            if (sweep is not None and k - sweep["s"] <= RECOVERY_WINDOW
                    and b.c[k] > sweep["range_low"] and b.v[k] >= SPRING_VOL_MULT * ma):
                low = min(b.l[sweep["s"]:k + 1])
                used_range_lows.add(sweep["range_low"])
                pending_entry = low - STOP_ATR_BUFFER * a
                sweep = None
    if pos is not None:
        if close_at_end:
            close(n - 1, b.c[n - 1], "end_of_data")
        elif open_out is not None:
            open_out.append({
                "entry_time": b.t[pos.entry_k].isoformat(),
                "entry": pos.entry,
                "stop": pos.stop,
                "initial_risk": pos.risk,
                "tp1_taken": pos.tp1,
                "size_left": pos.size,
                "pending_exit": pending_exit,
            })
    return trades


def _structure_break(p: Prepared, k: int, exit_tf: str) -> bool:
    if exit_tf == "1h":
        low_sw = p.swing_low[k]
        return low_sw is not None and p.b.c[k] < low_sw[0] <= p.b.c[k - 1]
    # v2: judged only when a 4h candle completes at this 1h close
    q = p.h4_done_at[k]
    if q < 1:
        return False
    low_sw = p.swing_low_4h[q]
    return low_sw is not None and p.b4.c[q] < low_sw[0] <= p.b4.c[q - 1]


def _track_sweep(p: Prepared, k: int, sweep: dict | None, used: set[float]) -> dict | None:
    if sweep is not None and k - sweep["s"] > RECOVERY_WINDOW:
        sweep = None
    if sweep is not None:
        return sweep
    last = p.h4_last[k]
    if last < RANGE_4H_BARS - 1 or p.atr4h[last] is None:
        return None
    lo = min(p.b4.l[last - RANGE_4H_BARS + 1:last + 1])
    hi = max(p.b4.h[last - RANGE_4H_BARS + 1:last + 1])
    if (hi - lo) > RANGE_MAX_ATR4H * p.atr4h[last] or lo in used:
        return None
    if p.b.l[k] < lo:
        return {"s": k, "range_low": lo}
    return None


@dataclass
class Stats:
    n: int = 0
    win: float = 0.0
    mean: float = 0.0
    total: float = 0.0
    pf: float = 0.0
    dd: float = 0.0
    pos_years: str = "0/0"
    extra: dict = field(default_factory=dict)


def stats(trades: list[Trade]) -> Stats:
    if not trades:
        return Stats()
    ordered = sorted(trades, key=lambda t: t.exit_time)
    rs = [t.r for t in ordered]
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    gains, losses = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    years = sorted({t.exit_time.year for t in ordered})
    pos_years = sum(1 for y in years if sum(t.r for t in ordered if t.exit_time.year == y) > 0)
    return Stats(len(rs), sum(r > 0 for r in rs) / len(rs), sum(rs) / len(rs), sum(rs),
                 gains / losses if losses else float("inf"), dd, f"{pos_years}/{len(years)}")


def row(name: str, s: Stats) -> str:
    if not s.n:
        return f"{name:<14}  no trades"
    return (f"{name:<14}{s.n:>5}  {100 * s.win:>5.1f}%  {s.mean:>+7.3f}R  {s.total:>+7.1f}R  "
            f"PF {s.pf:>4.2f}  DD {s.dd:>5.1f}R  yrs+ {s.pos_years}")


def gates(s: Stats, *, pooled: bool) -> list[str]:
    fails = []
    if pooled and s.n < 150:
        fails.append(f"trades {s.n}<150")
    if not pooled and s.n < 30:
        fails.append(f"trades {s.n}<30")
    if s.n and s.win < 0.80:
        fails.append(f"win {100 * s.win:.1f}%<80%")
    if s.n and s.mean < 0.25:
        fails.append(f"mean {s.mean:+.3f}<+0.25R")
    if s.n and s.pf <= 1.1:
        fails.append(f"PF {s.pf:.2f}<=1.1")
    if s.n and s.dd > 20:
        fails.append(f"DD {s.dd:.1f}>20R")
    if pooled and s.n:
        p, total = (int(x) for x in s.pos_years.split("/"))
        if total and p / total < 0.6:
            fails.append(f"positive years {s.pos_years}<60%")
    return fails
