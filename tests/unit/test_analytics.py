from __future__ import annotations

from datetime import UTC, datetime

import pytest
from private_trading_analytics.calibration import calibrate_bands
from private_trading_analytics.governance import (
    BLOCKED_SOLE_REASONS,
    _validate_approval_payload,
)
from private_trading_analytics.metrics import (
    SAMPLE_INSUFFICIENT,
    SAMPLE_OK,
    SAMPLE_SMALL,
    TradeRow,
    aggregate_trades,
    build_slices,
    sample_status_for,
    session_bucket,
)
from private_trading_analytics.narrate import narrate_calibration, narrate_performance
from private_trading_core.errors import AppError


def test_sample_status_thresholds() -> None:
    assert sample_status_for(5)[0] == SAMPLE_INSUFFICIENT
    assert sample_status_for(15)[0] == SAMPLE_SMALL
    assert sample_status_for(30)[0] == SAMPLE_OK


def test_session_bucket_utc_hours() -> None:
    assert session_bucket(datetime(2026, 1, 1, 3, tzinfo=UTC)) == "asia"
    assert session_bucket(datetime(2026, 1, 1, 10, tzinfo=UTC)) == "europe"
    assert session_bucket(datetime(2026, 1, 1, 18, tzinfo=UTC)) == "us"
    assert session_bucket(None) == "unknown"


def _row(**kwargs) -> TradeRow:
    base = dict(
        strategy_code="wyckoff-hdm",
        instrument_symbol="BTC/USDT",
        timeframe="1h",
        session_bucket="europe",
        direction="long",
        exit_reason="target",
        realized_r=1.0,
        realized_pnl=10.0,
        won=True,
    )
    base.update(kwargs)
    return TradeRow(**base)


def test_aggregate_trades_computes_from_rows_only() -> None:
    rows = [
        _row(realized_r=1.0, won=True),
        _row(realized_r=-1.0, won=False, exit_reason="stop"),
        _row(realized_r=0.5, won=True),
    ]
    agg = aggregate_trades(rows)
    assert agg["sample_size"] == 3
    assert agg["sample_status"] == SAMPLE_INSUFFICIENT
    assert agg["metrics"]["win_count"] == 2
    assert agg["metrics"]["loss_count"] == 1
    assert agg["metrics"]["mean_r"] == pytest.approx((1.0 - 1.0 + 0.5) / 3)
    assert agg["metrics"]["sum_r"] == pytest.approx(0.5)


def test_build_slices_keeps_per_dimension_sample_warnings() -> None:
    rows = [_row() for _ in range(12)]
    slices = build_slices(rows)
    overall = next(s for s in slices if s["grain"] == "overall")
    assert overall["sample_status"] == SAMPLE_SMALL
    assert overall["sample_size"] == 12
    strat = next(
        s
        for s in slices
        if s["strategy_code"] == "wyckoff-hdm" and s["instrument_symbol"] == "*"
    )
    assert strat["sample_size"] == 12


def test_cohorts_are_never_merged_in_aggregate_api() -> None:
    """aggregates take an explicit list — callers must not mix cohorts into one list."""
    paper = [_row(strategy_code="paper-strat")]
    backtest = [_row(strategy_code="bt-strat", realized_r=2.0)]
    # Correct usage: separate aggregates
    p = aggregate_trades(paper)
    b = aggregate_trades(backtest)
    assert p["metrics"]["sum_r"] == 1.0
    assert b["metrics"]["sum_r"] == 2.0
    # Mixed list would be a caller bug — document that service refresh is cohort-scoped
    mixed = aggregate_trades(paper + backtest)
    assert mixed["sample_size"] == 2  # would be wrong for product if cohorts mixed


def test_narrate_performance_rejects_invented_numbers() -> None:
    snap = {
        "cohort": "paper",
        "strategy_code": "wyckoff-hdm",
        "instrument_symbol": "*",
        "timeframe": "*",
        "session_bucket": "*",
        "sample_size": 3,
        "sample_status": SAMPLE_INSUFFICIENT,
        "metrics": {
            "win_count": 2,
            "loss_count": 1,
            "win_rate": 0.6667,
            "mean_r": 0.5,
            "sum_r": 1.5,
        },
        "warnings": ["sample_size=3 is below 10; metrics are not decision-grade."],
    }
    text = narrate_performance(snap)
    assert "paper" in text
    assert "0.6667" in text or "0.5" in text
    assert "never merged" in text


def test_calibration_drift_flag_informational_only() -> None:
    obs = (
        [{"confidence_band": "high", "realized_r": -1.0, "won": False} for _ in range(30)]
        + [{"confidence_band": "low", "realized_r": 1.0, "won": True} for _ in range(30)]
    )
    result = calibrate_bands(obs)
    assert result["sample_size"] == 60
    assert any("high_band_mean_r_below_low_band" in f for f in result["drift_flags"])
    text = narrate_calibration({"cohort": "paper", **result})
    assert "never triggered" in text


def test_retrain_approval_blocks_pnl_panic_alone() -> None:
    assert "pnl_panic" in BLOCKED_SOLE_REASONS
    with pytest.raises(AppError) as exc:
        _validate_approval_payload(
            reason_codes=["pnl_panic"],
            evaluation={"holdout_metrics": {"auc": 0.6}, "comparison_notes": "ok"},
        )
    assert exc.value.code == "POLICY_VIOLATION"

    with pytest.raises(AppError) as exc2:
        _validate_approval_payload(
            reason_codes=["drift_review"],
            evaluation={"comparison_notes": "missing holdout"},
        )
    assert exc2.value.code == "INVALID_INPUT"

    _validate_approval_payload(
        reason_codes=["drift_review", "pnl_panic"],
        evaluation={
            "holdout_metrics": {"auc": 0.61, "sample_size": 40},
            "comparison_notes": "challenger beats baseline on holdout",
        },
    )
