from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from private_trading_decision.labels import FEATURE_NAMES
from private_trading_decision.types import LabelClass, TrainingRow

DECISION_MODEL_VERSION = "0.1.0"

# Status code then numeric value. Unknown status is -1 so the model can abstain on missing inputs.
VECTOR_NAMES: tuple[str, ...] = tuple(
    name for feature in FEATURE_NAMES for name in (f"{feature}__status", f"{feature}__value")
)


def encode_features(features: dict[str, Any]) -> list[float]:
    vector: list[float] = []
    for name in FEATURE_NAMES:
        payload = features.get(name) or {}
        status = str(payload.get("status", "unknown"))
        raw = payload.get("value")
        try:
            numeric = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            numeric = 0.0
        if status == "true":
            vector.extend([1.0, numeric if numeric != 0.0 else 1.0])
        elif status == "false":
            vector.extend([0.0, numeric])
        else:
            vector.extend([-1.0, 0.0])
    return vector


def is_positive(row: TrainingRow) -> int:
    return 1 if row.label == LabelClass.WIN else 0


def rows_from_jsonl(payload: bytes) -> list[TrainingRow]:
    rows: list[TrainingRow] = []
    for line in payload.decode("utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        pnl = item.get("pnl_r")
        rows.append(
            TrainingRow(
                row_id=item["row_id"],
                bar_index=int(item["bar_index"]),
                open_time=datetime.fromisoformat(item["open_time"]),
                symbol=item["symbol"],
                timeframe=item["timeframe"],
                features=dict(item["features"]),
                feature_versions=dict(item.get("feature_versions") or {}),
                setup_state=item["setup_state"],
                direction=item["direction"],
                label=LabelClass(item["label"]),
                pnl_r=None if pnl is None else Decimal(str(pnl)),
                exit_reason=item.get("exit_reason"),
                entry_bar_index=item.get("entry_bar_index"),
                exit_bar_index=item.get("exit_bar_index"),
                strategy_code=item["strategy_code"],
                strategy_version_no=int(item["strategy_version_no"]),
                label_policy_id=item["label_policy_id"],
                label_policy_version=item["label_policy_version"],
                outcome_source=item["outcome_source"],
                source_bar_open_time=datetime.fromisoformat(item["source_bar_open_time"]),
                split=item.get("split"),
                fold_id=item.get("fold_id"),
                meta=dict(item.get("meta") or {}),
            )
        )
    return rows
