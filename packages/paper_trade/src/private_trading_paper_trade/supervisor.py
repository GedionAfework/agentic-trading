"""Paper supervisor service — gathers state, applies rules, pauses, alerts.

Safety contract (tested):
- May set ``paper_auto_open_enabled`` to false. Never sets it to true.
- Never opens, closes, cancels, or resizes a trade. Open trades keep being
  monitored to exit by ``paper.monitor``.
- Alerts only when a new warn/critical finding appears (or all clear), so a
  persistent problem does not spam Telegram every run.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from private_trading_db.models.market import Candle
from private_trading_db.models.ops import OutboxEvent, SystemSetting
from private_trading_db.models.paper import PaperTrade
from private_trading_db.models.scanner import ScanRun
from private_trading_market_data.catalog import get_instrument_by_symbol
from private_trading_market_data.quality import is_fresh
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_paper_trade.engine import STATUS_CLOSED
from private_trading_paper_trade.soak_metrics import ClosedSoakTrade
from private_trading_paper_trade.supervisor_rules import (
    Finding,
    ModelSample,
    SupervisorSnapshot,
    alert_text,
    alertable_keys,
    evaluate_supervisor,
    should_pause,
)

PAPER_AUTO_OPEN_KEY = "paper_auto_open_enabled"
SUPERVISOR_STATE_KEY = "paper_supervisor_state"
SUPERVISOR_ALERT_TOPIC = "ops.supervisor_alert"
SCAN_LOOKBACK_HOURS = 6


async def paper_auto_open_enabled(session: AsyncSession) -> bool:
    row = await session.get(SystemSetting, PAPER_AUTO_OPEN_KEY)
    if row is None or not isinstance(row.value, dict):
        return True
    return bool(row.value.get("enabled", True))


async def _pause_auto_open(
    session: AsyncSession, *, reasons: list[str], now: datetime
) -> None:
    value = {
        "enabled": False,
        "paused_by": "supervisor",
        "paused_at": now.isoformat(),
        "reasons": reasons,
    }
    row = await session.get(SystemSetting, PAPER_AUTO_OPEN_KEY)
    if row is None:
        session.add(SystemSetting(key=PAPER_AUTO_OPEN_KEY, value=value, updated_by=None))
    else:
        row.value = value
        row.updated_by = None


async def _model_samples(
    session: AsyncSession, *, owner_user_id: uuid.UUID
) -> list[ModelSample]:
    from private_trading_paper_trade.service import soak_trade_model_code

    rows = await session.execute(
        select(PaperTrade)
        .where(
            PaperTrade.owner_user_id == owner_user_id,
            PaperTrade.status == STATUS_CLOSED,
            PaperTrade.realized_r.is_not(None),
        )
        .order_by(PaperTrade.closed_at.asc().nulls_last(), PaperTrade.created_at.asc())
    )
    grouped: dict[str, list[ClosedSoakTrade]] = {}
    for trade in rows.scalars().all():
        code = soak_trade_model_code(trade.fill_model)
        if code is None:
            continue
        extra = dict(trade.fill_model or {}).get("soak_fill", {}).get(
            "extra_cost_bps_vs_research"
        )
        grouped.setdefault(code, []).append(
            ClosedSoakTrade(
                realized_r=float(trade.realized_r),
                closed_at=trade.closed_at or trade.exit_bar_open_time,
                extra_cost_bps_vs_research=None if extra is None else float(extra),
            )
        )
    return [ModelSample(code=code, trades=trades) for code, trades in sorted(grouped.items())]


async def _challenger_samples(session: AsyncSession) -> list[ModelSample]:
    """Challenger virtual ledgers, judged by the same kill rules but alert-only."""
    from private_trading_paper_trade.challenger import challenger_status

    out: list[ModelSample] = []
    for state in await challenger_status(session):
        rows = state.get("trades") or []
        if not rows:
            continue
        out.append(
            ModelSample(
                code=f"{state['code']}-v{state['version_no']} (challenger)",
                trades=[
                    ClosedSoakTrade(
                        realized_r=float(r["r"]),
                        closed_at=datetime.fromisoformat(r["exit_time"]),
                        extra_cost_bps_vs_research=None,
                    )
                    for r in rows
                ],
                alert_only=True,
            )
        )
    return out


async def _stale_symbols(session: AsyncSession, *, now: datetime) -> list[str]:
    from private_trading_strategies.soak_freeze import owner_test_symbols

    stale: list[str] = []
    for symbol in owner_test_symbols():
        instrument = await get_instrument_by_symbol(session, symbol)
        last_open = None
        if instrument is not None:
            last_open = (
                await session.execute(
                    select(func.max(Candle.open_time)).where(
                        Candle.instrument_id == instrument.id,
                        Candle.timeframe == "1h",
                        Candle.is_final.is_(True),
                    )
                )
            ).scalar_one_or_none()
        if not is_fresh(timeframe="1h", last_open_time=last_open, now=now):
            stale.append(symbol)
    return stale


async def collect_snapshot(
    session: AsyncSession, *, owner_user_id: uuid.UUID, now: datetime
) -> SupervisorSnapshot:
    from private_trading_risk.portfolio import PortfolioRiskPolicy

    from private_trading_paper_trade.service import (
        get_account,
        integrity_report,
        paper_portfolio_state,
    )

    account = await get_account(session, owner_user_id=owner_user_id)
    defects: list[str] = []
    if account is not None:
        defects = list((await integrity_report(session, account_id=account.id))["defects"])
    _exposures, daily_pnl = await paper_portfolio_state(session, owner_user_id=owner_user_id)
    failed = (
        await session.execute(
            select(func.count(ScanRun.id)).where(
                ScanRun.status == "failed",
                ScanRun.created_at >= now - timedelta(hours=SCAN_LOOKBACK_HOURS),
            )
        )
    ).scalar_one()
    samples = await _model_samples(session, owner_user_id=owner_user_id)
    samples.extend(await _challenger_samples(session))
    return SupervisorSnapshot(
        samples=samples,
        stale_symbols=await _stale_symbols(session, now=now),
        integrity_defects=defects,
        failed_scan_runs=int(failed or 0),
        scan_lookback_hours=SCAN_LOOKBACK_HOURS,
        daily_loss_stop_hit=daily_pnl <= -PortfolioRiskPolicy().max_daily_loss_pct,
        auto_open_enabled=await paper_auto_open_enabled(session),
    )


def plan_actions(
    findings: list[Finding],
    *,
    previous_keys: set[str],
    auto_open_enabled: bool,
) -> dict[str, Any]:
    """Pure decision: what to pause and what to alert. Never resumes."""
    current = alertable_keys(findings)
    new = [f for f in findings if f.key in current - previous_keys]
    cleared = sorted(previous_keys - current)
    pause = auto_open_enabled and should_pause(findings)
    send = bool(new) or pause or (bool(previous_keys) and not current)
    return {
        "pause": pause,
        "new": new,
        "cleared": cleared,
        "send_alert": send,
        "current_keys": sorted(current),
    }


async def run_supervisor(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(UTC)
    snapshot = await collect_snapshot(session, owner_user_id=owner_user_id, now=current_time)
    findings = evaluate_supervisor(snapshot)

    state_row = await session.get(SystemSetting, SUPERVISOR_STATE_KEY)
    previous = dict(state_row.value) if state_row is not None and state_row.value else {}
    plan = plan_actions(
        findings,
        previous_keys=set(previous.get("alert_keys") or []),
        auto_open_enabled=snapshot.auto_open_enabled,
    )
    if plan["pause"]:
        await _pause_auto_open(
            session,
            reasons=[f.key for f in findings if f.pauses_auto_open],
            now=current_time,
        )
    if plan["send_alert"]:
        text = alert_text(plan["new"], paused_now=plan["pause"], cleared=plan["cleared"])
        session.add(
            OutboxEvent(
                topic=SUPERVISOR_ALERT_TOPIC,
                aggregate_type="paper_supervisor",
                aggregate_id=owner_user_id,
                payload={
                    "owner_user_id": str(owner_user_id),
                    "text": text,
                    "finding_keys": plan["current_keys"],
                    "paused": plan["pause"],
                },
            )
        )
    state = {
        "last_run_at": current_time.isoformat(),
        "alert_keys": plan["current_keys"],
        "findings": [f.as_dict() for f in findings],
        "paused_this_run": plan["pause"],
        "alert_sent": plan["send_alert"],
        "models": [
            {
                "code": s.code,
                "closed_trades": s.n,
                "mean_r": round(s.mean_r, 4),
                "max_drawdown_r": round(s.drawdown_r, 4),
                "avg_extra_cost_bps": s.avg_extra_cost_bps,
            }
            for s in snapshot.samples
        ],
    }
    if state_row is None:
        session.add(SystemSetting(key=SUPERVISOR_STATE_KEY, value=state, updated_by=None))
    else:
        state_row.value = state
    await session.commit()
    return state


async def supervisor_status(session: AsyncSession) -> dict[str, Any]:
    state_row = await session.get(SystemSetting, SUPERVISOR_STATE_KEY)
    switch_row = await session.get(SystemSetting, PAPER_AUTO_OPEN_KEY)
    switch = dict(switch_row.value) if switch_row is not None and switch_row.value else {}
    return {
        "paper_auto_open_enabled": bool(switch.get("enabled", True)),
        "paused_by": switch.get("paused_by"),
        "paused_at": switch.get("paused_at"),
        "pause_reasons": list(switch.get("reasons") or []),
        "last_run": dict(state_row.value) if state_row is not None and state_row.value else None,
        "note": (
            "The supervisor can pause new paper auto-opens and alert. It never resumes, "
            "opens, closes, or resizes trades. Resume via PUT /v1/scanner/switches "
            "(paper_auto_open_enabled=true) or /settings paper on."
        ),
    }
