"""Forward paper challenger ledger — DOGE NaolDesk breakout v2.

Owner decision 2026-11-04 (option 2): run DOGE breakout v2 as a paper-only
challenger next to DOGE V1. Because the paper account allows one position per
coin, the challenger keeps its own virtual ledger: every run replays the
**frozen** simulator (private_trading_backtest.naoldesk — the exact code that
produced the backtest) over DOGE candles that opened on/after FORWARD_START.

Read-only with respect to trading: it never opens, sizes, or closes a real
paper trade and never publishes alerts. It only writes its own ledger row.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from private_trading_backtest import naoldesk as nd
from private_trading_db.models.market import Candle
from private_trading_db.models.ops import SystemSetting
from private_trading_db.models.paper import PaperTrade
from private_trading_market_data.catalog import get_instrument_by_symbol
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_paper_trade.engine import STATUS_CLOSED

CHALLENGER: dict[str, Any] = {
    "code": "doge-naoldesk-breakout",
    "version_no": 2,
    "symbol": "DOGE/USDT",
    "setup": "A",
    "exit_tf": "4h",
    "label": "DOGE NaolDesk breakout v2 (challenger)",
    "incumbent_code": "doge-mtf-bos-volume-profit",
    # First candle that counts. Chosen when the owner approved, never moved.
    "forward_start": datetime(2026, 11, 5, tzinfo=UTC),
    "paper_only": True,
    "live_alerts_allowed": False,
    "research": {
        "trades": 116,
        "win_rate": 0.500,
        "mean_r": 0.282,
        "profit_factor": 1.54,
        "max_drawdown_r": 13.0,
        "method": "fixed rules 2022-2026; best of 5 coins after one revision (spent data)",
    },
}
LEDGER_KEY = f"paper_challenger:{CHALLENGER['code']}-v{CHALLENGER['version_no']}"
WARMUP = timedelta(days=120)  # daily EMA50 + 10-day slope + 30 x 4h range


async def _load(session: AsyncSession, instrument_id: uuid.UUID, tf: str, since: datetime):
    rows = (
        await session.execute(
            select(Candle)
            .where(
                Candle.instrument_id == instrument_id,
                Candle.timeframe == tf,
                Candle.is_final.is_(True),
                Candle.open_time >= since,
            )
            .order_by(Candle.open_time)
        )
    ).scalars().all()
    return nd.Bars(
        [r.open_time if r.open_time.tzinfo else r.open_time.replace(tzinfo=UTC) for r in rows],
        [float(r.open) for r in rows],
        [float(r.high) for r in rows],
        [float(r.low) for r in rows],
        [float(r.close) for r in rows],
        [float(r.volume or 0) for r in rows],
    )


def daily_from_hourly(b: nd.Bars) -> nd.Bars:
    """UTC daily candles from complete 24-hour days only (matches Binance 1d)."""
    days: dict[datetime, list[int]] = defaultdict(list)
    for i, t in enumerate(b.t):
        days[t.replace(hour=0, minute=0, second=0, microsecond=0)].append(i)
    out: list[list] = [[], [], [], [], [], []]
    for day in sorted(days):
        idx = days[day]
        if len(idx) != 24:
            continue
        vals = (
            day,
            b.o[idx[0]],
            max(b.h[i] for i in idx),
            min(b.l[i] for i in idx),
            b.c[idx[-1]],
            sum(b.v[i] for i in idx),
        )
        for col, val in zip(out, vals, strict=True):
            col.append(val)
    return nd.Bars(*out)


def summarize(trades: list[nd.Trade]) -> dict[str, Any]:
    s = nd.stats(trades)
    return {
        "closed_trades": s.n,
        "win_rate": s.win if s.n else None,
        "mean_r": s.mean if s.n else None,
        "total_r": s.total,
        "profit_factor": None if not s.n or s.pf == float("inf") else s.pf,
        "max_drawdown_r": s.dd,
    }


async def _incumbent_forward(session: AsyncSession, *, owner_user_id: uuid.UUID | None):
    if owner_user_id is None:
        return {"closed_trades": 0, "win_rate": None, "mean_r": None}
    from private_trading_paper_trade.service import soak_trade_model_code

    rows = (
        await session.execute(
            select(PaperTrade).where(
                PaperTrade.owner_user_id == owner_user_id,
                PaperTrade.instrument_symbol == CHALLENGER["symbol"],
                PaperTrade.status == STATUS_CLOSED,
                PaperTrade.realized_r.is_not(None),
                PaperTrade.closed_at >= CHALLENGER["forward_start"],
            )
        )
    ).scalars().all()
    rs = [
        float(t.realized_r)
        for t in rows
        if soak_trade_model_code(t.fill_model) == CHALLENGER["incumbent_code"]
    ]
    n = len(rs)
    return {
        "closed_trades": n,
        "win_rate": sum(r > 0 for r in rs) / n if n else None,
        "mean_r": sum(rs) / n if n else None,
    }


async def run_challenger_ledger(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    start: datetime = CHALLENGER["forward_start"]
    state: dict[str, Any] = {
        "code": CHALLENGER["code"],
        "version_no": CHALLENGER["version_no"],
        "symbol": CHALLENGER["symbol"],
        "label": CHALLENGER["label"],
        "forward_start": start.isoformat(),
        "last_run_at": current.isoformat(),
        "paper_only": True,
        "live_alerts_allowed": False,
        "research": CHALLENGER["research"],
    }
    instrument = await get_instrument_by_symbol(session, CHALLENGER["symbol"])
    if instrument is None:
        state["status"] = "no_instrument"
    else:
        since = start - WARMUP
        one = await _load(session, instrument.id, "1h", since)
        four = await _load(session, instrument.id, "4h", since)
        if not one.t or one.t[-1] < start:
            state["status"] = "waiting_for_forward_candles"
            trades, opened = [], []
        else:
            prepared = nd.prepare(one, four, daily_from_hourly(one))
            opened = []
            trades = nd.simulate(
                "DOGE",
                prepared,
                CHALLENGER["setup"],
                exit_tf=CHALLENGER["exit_tf"],
                score_start=start,
                close_at_end=False,
                open_out=opened,
            )
            state["status"] = "running"
            state["last_candle"] = one.t[-1].isoformat()
        state["challenger"] = summarize(trades)
        state["trades"] = [
            {
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "r": round(t.r, 4),
                "reason": t.reason,
                "tp1": t.tp1,
            }
            for t in trades
        ]
        state["open_position"] = opened[0] if opened else None
    state["incumbent"] = {
        "code": CHALLENGER["incumbent_code"],
        **await _incumbent_forward(session, owner_user_id=owner_user_id),
    }
    state["note"] = (
        "Forward-only virtual ledger from the frozen backtest code. Paper only; "
        "never opens real paper trades or alerts. Judge after >= 30 closed trades each."
    )
    row = await session.get(SystemSetting, LEDGER_KEY)
    if row is None:
        session.add(SystemSetting(key=LEDGER_KEY, value=state, updated_by=None))
    else:
        row.value = state
    await session.commit()
    return state


async def challenger_status(session: AsyncSession) -> list[dict[str, Any]]:
    row = await session.get(SystemSetting, LEDGER_KEY)
    if row is None or not row.value:
        return [
            {
                "code": CHALLENGER["code"],
                "version_no": CHALLENGER["version_no"],
                "symbol": CHALLENGER["symbol"],
                "label": CHALLENGER["label"],
                "forward_start": CHALLENGER["forward_start"].isoformat(),
                "status": "not_run_yet",
                "research": CHALLENGER["research"],
                "paper_only": True,
                "live_alerts_allowed": False,
            }
        ]
    return [dict(row.value)]
