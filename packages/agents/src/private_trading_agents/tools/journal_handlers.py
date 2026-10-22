"""AG-08 journal tool handlers — read-only aggregates + grounded narration."""

from __future__ import annotations

from typing import Any

from private_trading_agents.tools.journal_schemas import (
    JournalNarrateIn,
    JournalNarrateOut,
    JournalSummarizeIn,
    JournalSummarizeOut,
)


def handle_journal_summarize_metrics(
    payload: JournalSummarizeIn,
) -> JournalSummarizeOut:
    # Lazy import: analytics depends on agents; avoid import cycle at module load.
    from private_trading_analytics.metrics import TradeRow, aggregate_trades

    rows = [
        TradeRow(
            strategy_code=row.strategy_code,
            instrument_symbol=row.instrument_symbol,
            timeframe=row.timeframe,
            session_bucket=row.session_bucket,
            direction=row.direction,
            exit_reason=row.exit_reason,
            realized_r=row.realized_r,
            realized_pnl=row.realized_pnl,
            won=row.won,
        )
        for row in payload.trades
    ]
    agg = aggregate_trades(rows)
    return JournalSummarizeOut(
        cohort=payload.cohort,
        strategy_code=payload.strategy_code,
        instrument_symbol=payload.instrument_symbol,
        timeframe=payload.timeframe,
        session_bucket=payload.session_bucket,
        sample_size=int(agg["sample_size"]),
        sample_status=str(agg["sample_status"]),
        metrics=dict(agg.get("metrics") or {}),
        warnings=list(agg.get("warnings") or []),
        merges_cohorts=False,
    )


def handle_journal_narrate_performance(
    payload: JournalNarrateIn,
) -> JournalNarrateOut:
    from private_trading_analytics.narrate import narrate_performance

    snapshot: dict[str, Any] = dict(payload.snapshot)
    if "cohort" not in snapshot:
        raise ValueError("snapshot.cohort is required")
    narrative = narrate_performance(snapshot)
    return JournalNarrateOut(
        narrative=narrative,
        explanation_source="deterministic",
        authorizes_trade=False,
        kind="performance",
    )


def handle_journal_narrate_calibration(
    payload: JournalNarrateIn,
) -> JournalNarrateOut:
    from private_trading_analytics.narrate import narrate_calibration

    snapshot: dict[str, Any] = dict(payload.snapshot)
    if "cohort" not in snapshot:
        raise ValueError("snapshot.cohort is required")
    if "band_field" not in snapshot:
        raise ValueError("snapshot.band_field is required")
    narrative = narrate_calibration(snapshot)
    return JournalNarrateOut(
        narrative=narrative,
        explanation_source="deterministic",
        authorizes_trade=False,
        kind="calibration",
    )
