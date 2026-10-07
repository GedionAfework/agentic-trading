from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Literal

from private_trading_features.engine import FEATURE_ENGINE_VERSION
from private_trading_features.types import CandleBar
from private_trading_risk.policy import RISK_ENGINE_VERSION
from private_trading_strategies.evaluate import STRATEGY_ENGINE_VERSION

from private_trading_decision.labels import FEATURE_NAMES, feature_schema, label_bar
from private_trading_decision.quality import quality_report
from private_trading_decision.splits import (
    TimeSplitConfig,
    WalkForwardConfig,
    assign_time_splits,
    assign_walk_forward,
    assert_no_time_leakage,
)
from private_trading_decision.types import DatasetBuildResult, LabelPolicy, TrainingRow

DATASET_BUILDER_VERSION = "0.1.0"


def _row_to_dict(row: TrainingRow) -> dict[str, Any]:
    return {
        "row_id": row.row_id,
        "bar_index": row.bar_index,
        "open_time": row.open_time.isoformat(),
        "source_bar_open_time": row.source_bar_open_time.isoformat(),
        "symbol": row.symbol,
        "timeframe": row.timeframe,
        "features": row.features,
        "feature_versions": row.feature_versions,
        "setup_state": row.setup_state,
        "direction": row.direction,
        "label": row.label.value,
        "pnl_r": None if row.pnl_r is None else str(row.pnl_r),
        "exit_reason": row.exit_reason,
        "entry_bar_index": row.entry_bar_index,
        "exit_bar_index": row.exit_bar_index,
        "strategy_code": row.strategy_code,
        "strategy_version_no": row.strategy_version_no,
        "label_policy_id": row.label_policy_id,
        "label_policy_version": row.label_policy_version,
        "outcome_source": row.outcome_source,
        "split": row.split,
        "fold_id": row.fold_id,
        "meta": row.meta,
    }


def rows_fingerprint(rows: list[TrainingRow], *, label_policy: dict[str, Any]) -> str:
    payload = {
        "label_policy": label_policy,
        "feature_names": list(FEATURE_NAMES),
        "rows": [_row_to_dict(r) for r in rows],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_training_dataset(
    bars: list[CandleBar],
    *,
    symbol: str,
    timeframe: str,
    source_dataset_fingerprint: str,
    policy: LabelPolicy | None = None,
    split_mode: Literal["time", "walk_forward"] = "time",
    min_lookback: int = 25,
) -> DatasetBuildResult:
    """Build leakage-safe tabular rows. Features use bars[:i+1] only via feature engine."""
    policy = policy or LabelPolicy()
    rows: list[TrainingRow] = []
    last_index = len(bars) - 1
    # Need room for next_open entry; labels may SKIPPED near the end
    for i in range(min_lookback, last_index):
        rows.append(
            label_bar(
                bars,
                i,
                symbol=symbol,
                timeframe=timeframe,
                policy=policy,
            )
        )

    if split_mode == "walk_forward":
        rows, split_manifest = assign_walk_forward(rows, config=WalkForwardConfig())
    else:
        rows, split_manifest = assign_time_splits(rows, config=TimeSplitConfig())

    assert_no_time_leakage(rows)
    label_policy = policy.to_dict()
    schema = feature_schema()
    q = quality_report(rows)
    engines = {
        "dataset_builder_version": DATASET_BUILDER_VERSION,
        "feature_engine_version": FEATURE_ENGINE_VERSION,
        "strategy_engine_version": STRATEGY_ENGINE_VERSION,
        "risk_engine_version": RISK_ENGINE_VERSION,
    }
    fp = rows_fingerprint(rows, label_policy=label_policy)
    return DatasetBuildResult(
        rows=rows,
        fingerprint=fp,
        feature_schema=schema,
        split_manifest=split_manifest,
        quality_report=q,
        engine_versions=engines,
        label_policy=label_policy,
        source_dataset_fingerprint=source_dataset_fingerprint,
    )


def serialize_rows_jsonl(rows: list[TrainingRow]) -> bytes:
    lines = [json.dumps(_row_to_dict(r), sort_keys=True, default=str) for r in rows]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
