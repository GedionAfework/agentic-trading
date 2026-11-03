"""Coin desk — "status of my 4 coins" and "why WAIT / why ENTER" per coin.

Read-only copilot surface over computed state: last closed-candle scan,
model routing, open paper trade, portfolio gate, supervisor pause, soak
progress. Text is built only from those fields (no LLM, no invented numbers).
It never authorizes, opens, or closes a trade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from private_trading_strategies.multi_market import PAPER_MODEL_REGISTRY, TradingObjective

DESK_TIMEFRAME = "1h"
SCAN_STALE_AFTER = timedelta(hours=3)

# Honest per-coin context from docs/strategy/BACKTEST_FINDINGS.md.
COIN_CONTEXT: dict[str, str] = {
    "SOL/USDT": "Primary soak incumbent (V1 expectancy / V2 win rate).",
    "DOGE/USDT": (
        "On probation: walk-forward passed overall, but 2025–2026 folds were "
        "negative. Paper soak must confirm."
    ),
    "BTC/USDT": (
        "Watch only: every tested strategy family failed after costs. "
        "Stays WAIT until a new hypothesis passes walk-forward."
    ),
    "ETH/USDT": (
        "Watch only: every tested strategy family failed after costs. "
        "Stays WAIT until a new hypothesis passes walk-forward."
    ),
}

STATUS_TEXT: dict[str, str] = {
    "skipped_stale": "Market data is stale or not actionable, so no decision was made.",
    "skipped_insufficient_bars": "Not enough closed candles yet to evaluate.",
    "regime_unknown": "Not enough history to classify the market regime.",
    "no_validated_model": "No validated paper model for this coin in the current regime/profile.",
    "prefilter_no_setup": "No break of structure on the last closed candle.",
    "specialist_wait": "The specialist model's conditions are not met.",
    "unsupported_multi_market_timeframe": "This timeframe is not used for paper models.",
    "failed": "The scan failed; check scanner status.",
}

BLOCKER_TEXT: dict[str, str] = {
    "stale_market_data": "market data is stale",
    "market_not_actionable": "market is not actionable",
    "missing_entry": "no valid entry level",
    "missing_invalidation": "no structural invalidation (stop) level",
    "missing_target_1": "no first target",
    "entry_equals_stop": "entry equals stop",
    "stop_wrong_side_of_entry": "stop is on the wrong side of entry",
    "model_abstain": "the ranking model abstained",
    "symbol_already_open": "a paper position is already open",
    "daily_loss_stop": "the daily loss stop is hit",
    "total_open_risk_exceeded": "total open risk cap is full",
    "crypto_cluster_risk_exceeded": "crypto cluster cap is full (coins move together)",
    "volume_gate_failed": "volume did not confirm (no effort behind the move)",
    "breakout_not_confirmed": "breakout not confirmed on a closed candle",
    "higher_timeframe_trend_unknown": "higher-timeframe trend is unclear",
    "regime_not_allowed": "the current regime is not one the model trades",
    "PAPER_AUTO_OPEN_PAUSED": "paper auto-open is paused by the supervisor/owner",
    "PAPER_PORTFOLIO_VETO": "the portfolio gate refused the open",
}


def _note_value(notes: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for note in notes:
        if note.startswith(prefix):
            return note[len(prefix) :]
    return None


def coin_role(symbol: str, objective: TradingObjective) -> dict[str, Any]:
    """How this coin is routed for the selected profile (from the registry)."""
    specs = [s for s in PAPER_MODEL_REGISTRY if s.symbol == symbol and s.validated_for_paper]
    active = [s for s in specs if s.objective == objective]
    if active:
        spec = active[0]
        return {
            "role": "paper",
            "model_code": spec.code,
            "regimes": [r.value for r in spec.regimes],
            "research": {
                "trades": spec.validation.trades,
                "win_rate": spec.validation.win_rate,
                "mean_r": spec.validation.mean_r,
            },
            "note": "",
        }
    if specs:
        others = sorted({s.objective.value for s in specs})
        return {
            "role": "inactive_for_profile",
            "model_code": None,
            "regimes": [],
            "research": None,
            "note": (
                f"Only has a {'/'.join(others)} model; the selected profile is "
                f"'{objective.value}', so this coin stays WAIT."
            ),
        }
    return {"role": "watch", "model_code": None, "regimes": [], "research": None, "note": ""}


def describe_coin(
    symbol: str,
    *,
    objective: TradingObjective,
    last_run: dict[str, Any] | None,
    open_trade: dict[str, Any] | None,
    portfolio_row: dict[str, Any] | None,
    auto_open_enabled: bool,
    now: datetime,
) -> dict[str, Any]:
    """Pure: one coin's verdict + plain-language reasons."""
    role = coin_role(symbol, objective)
    reasons: list[str] = []
    levels = None
    if open_trade is not None:
        headline = "IN PAPER TRADE"
        reasons.append(
            f"{open_trade.get('status', 'open')} paper {open_trade.get('direction', 'long')} "
            f"via {open_trade.get('model_code') or 'model'}: entry {open_trade.get('entry')}, "
            f"stop {open_trade.get('stop')}, target {open_trade.get('target')}."
        )
    elif last_run is None:
        headline = "NO SCAN YET"
        reasons.append("No closed-candle scan recorded for this coin.")
    else:
        details = dict(last_run.get("details") or {})
        notes = list(details.get("notes") or [])
        action = last_run.get("action") or "WAIT"
        status = str(last_run.get("status") or "")
        headline = action
        if status in STATUS_TEXT:
            reasons.append(STATUS_TEXT[status])
        regime = _note_value(notes, "regime")
        if status == "no_validated_model" and regime:
            reasons.append(f"Current regime: {regime}.")
        for code in details.get("reasons") or []:
            reasons.append(BLOCKER_TEXT.get(code, code.replace("_", " ")).capitalize() + ".")
        if action == "ENTER":
            levels = details.get("levels")
            blocked = details.get("paper_open_blocked")
            if blocked:
                headline = "ENTER (not opened)"
                reasons.append(
                    "Signal fired but no paper trade opened: "
                    + BLOCKER_TEXT.get(blocked, str(blocked))
                    + "."
                )
            elif details.get("paper_trade_id"):
                reasons.append("Signal fired and a paper trade was opened.")
        elif not details.get("reasons") and details.get("explanation"):
            reasons.append(str(details["explanation"]))
        candle = last_run.get("candle_open_time")
        if isinstance(candle, datetime) and now - candle > SCAN_STALE_AFTER:
            reasons.append(
                f"Last scan is for the {candle:%Y-%m-%d %H:%M} UTC candle; "
                "is the scanner running?"
            )
    if role["role"] == "watch" and open_trade is None:
        headline = "WATCH" if headline in ("WAIT", "NO_SETUP", "NO SCAN YET") else headline
    if role["note"]:
        reasons.append(role["note"])
    if role["role"] == "paper" and not auto_open_enabled:
        reasons.append("Paper auto-open is paused: new signals are recorded but not opened.")
    if portfolio_row is not None and not portfolio_row.get("portfolio_allows_open", True):
        blockers = [BLOCKER_TEXT.get(b, b) for b in portfolio_row.get("blockers") or []]
        if open_trade is None and blockers:
            reasons.append("Portfolio would refuse a new open now: " + "; ".join(blockers) + ".")
    return {
        "symbol": symbol,
        "headline": headline,
        "role": role["role"],
        "model_code": role["model_code"],
        "regimes": role["regimes"],
        "research": role["research"],
        "context": COIN_CONTEXT.get(symbol, ""),
        "last_scan": None
        if last_run is None
        else {
            "candle_open_time": _iso(last_run.get("candle_open_time")),
            "status": last_run.get("status"),
            "action": last_run.get("action"),
        },
        "levels": levels,
        "open_trade": open_trade,
        "reasons": reasons,
        "authorizes_trade": False,
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


_ICON = {
    "ENTER": "🟢",
    "ENTER (not opened)": "🟡",
    "IN PAPER TRADE": "🔵",
    "WATCH": "👁",
}


def narrate_desk(view: dict[str, Any]) -> str:
    """Compact Telegram HTML summary of all coins."""
    lines = [f"<b>Coin desk</b> · profile <b>{view['profile']['objective']}</b>"]
    if not view["supervisor"]["paper_auto_open_enabled"]:
        lines.append("🛑 Paper auto-open paused by supervisor/owner.")
    for coin in view["coins"]:
        icon = _ICON.get(coin["headline"], "⚪")
        first = coin["reasons"][0] if coin["reasons"] else ""
        lines.append(f"{icon} <b>{coin['symbol']}</b> {coin['headline']} · {first}")
    regime = view.get("btc_regime") or {}
    if regime:
        lines.append(
            f"BTC regime (shadow, not a filter): <b>{regime.get('label', 'unknown')}</b>"
        )
    soak = view.get("soak") or {}
    if soak:
        lines.append(
            f"Soak {soak.get('model_code')}: {soak.get('closed_trades', 0)}/"
            f"{soak.get('min_closed_trades')} closed, mean {float(soak.get('mean_r') or 0):+.3f}R."
        )
    lines.append("Details: <code>/why sol</code>. Paper only; not a trade instruction.")
    return "\n".join(lines)


def narrate_coin(coin: dict[str, Any]) -> str:
    lines = [f"<b>{coin['symbol']}</b> · {coin['headline']} · role {coin['role']}"]
    if coin["context"]:
        lines.append(coin["context"])
    for reason in coin["reasons"]:
        lines.append(f"• {reason}")
    levels = coin.get("levels")
    if levels:
        lines.append(
            f"Levels: entry {levels.get('entry')}, stop {levels.get('stop')}, "
            f"target {levels.get('target')} (R:R {levels.get('rr')})."
        )
    research = coin.get("research")
    if research:
        lines.append(
            f"Research ({coin['model_code']}): {research['trades']} trades, "
            f"{research['win_rate'] * 100:.1f}% wins, {research['mean_r']:+.3f}R."
        )
    lines.append("Paper only; not a trade instruction.")
    return "\n".join(lines)


def resolve_coin(raw: str, symbols: tuple[str, ...]) -> str | None:
    key = raw.strip().upper().replace("-", "/")
    for symbol in symbols:
        if key in (symbol, symbol.split("/")[0]):
            return symbol
    return None


async def coin_desk_status(session: Any, *, owner_user_id: uuid.UUID) -> dict[str, Any]:
    """Load state and describe every owner coin. Read-only."""
    from private_trading_db.models.paper import PaperTrade
    from private_trading_db.models.scanner import ScanRun
    from private_trading_paper_trade.btc_shadow import btc_regime_shadow_report
    from private_trading_paper_trade.engine import STATUS_OPEN, STATUS_READY
    from private_trading_paper_trade.service import (
        portfolio_status,
        soak_step1_progress,
        soak_trade_model_code,
    )
    from private_trading_paper_trade.supervisor import supervisor_status
    from private_trading_paper_trade.trading_profile import trading_profile_status
    from private_trading_strategies.soak_freeze import owner_test_symbols
    from sqlalchemy import select

    now = datetime.now(UTC)
    profile = await trading_profile_status(session)
    objective = TradingObjective(profile["selected_objective"])
    supervisor = await supervisor_status(session)
    portfolio = await portfolio_status(session, owner_user_id=owner_user_id)
    by_symbol = {row["symbol"]: row for row in portfolio["symbols"]}

    open_rows = await session.execute(
        select(PaperTrade).where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.status.in_((STATUS_READY, STATUS_OPEN)),
        )
    )
    open_trades = {
        t.instrument_symbol: {
            "status": t.status,
            "direction": t.direction,
            "model_code": soak_trade_model_code(t.fill_model),
            "entry": None if t.entry_price is None else str(t.entry_price),
            "planned_entry": str(t.planned_entry),
            "stop": str(t.stop_price),
            "target": str(t.target_price),
            "bars_held": t.bars_held,
        }
        for t in open_rows.scalars().all()
    }
    coins = []
    for symbol in owner_test_symbols():
        run = (
            await session.execute(
                select(ScanRun)
                .where(
                    ScanRun.instrument_symbol == symbol,
                    ScanRun.timeframe == DESK_TIMEFRAME,
                )
                .order_by(ScanRun.candle_open_time.desc(), ScanRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        last_run = (
            None
            if run is None
            else {
                "candle_open_time": run.candle_open_time,
                "status": run.status,
                "action": run.action,
                "details": dict(run.details or {}),
            }
        )
        coins.append(
            describe_coin(
                symbol,
                objective=objective,
                last_run=last_run,
                open_trade=open_trades.get(symbol),
                portfolio_row=by_symbol.get(symbol),
                auto_open_enabled=bool(supervisor["paper_auto_open_enabled"]),
                now=now,
            )
        )
    soak = await soak_step1_progress(session, owner_user_id=owner_user_id)
    latest_tagged = (
        await session.execute(
            select(ScanRun)
            .where(ScanRun.details["btc_regime"].astext.is_not(None))
            .order_by(ScanRun.candle_open_time.desc(), ScanRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    btc_regime = (
        dict(latest_tagged.details.get("btc_regime") or {}) if latest_tagged else {}
    )
    return {
        "generated_at": now.isoformat(),
        "profile": {
            "objective": objective.value,
            "model_code": profile["selected_code"],
        },
        "supervisor": {
            "paper_auto_open_enabled": supervisor["paper_auto_open_enabled"],
            "pause_reasons": supervisor["pause_reasons"],
        },
        "portfolio": {
            "crypto_open_risk_pct": portfolio["crypto_open_risk_pct"],
            "crypto_headroom_pct": portfolio["crypto_headroom_pct"],
            "daily_loss_stop_hit": portfolio["daily_loss_stop_hit"],
        },
        "soak": {
            "model_code": soak.get("model_code"),
            "closed_trades": soak.get("closed_trades"),
            "min_closed_trades": soak.get("min_closed_trades"),
            "mean_r": soak.get("mean_r"),
            "win_rate": soak.get("win_rate"),
        },
        "coins": coins,
        "btc_regime": btc_regime,
        "btc_regime_shadow": await btc_regime_shadow_report(
            session, owner_user_id=owner_user_id
        ),
        "authorizes_trade": False,
    }
