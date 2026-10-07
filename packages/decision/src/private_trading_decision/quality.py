from __future__ import annotations

from collections import Counter
from typing import Any

from private_trading_decision.types import LabelClass, TrainingRow


def quality_report(rows: list[TrainingRow]) -> dict[str, Any]:
    labels = Counter(r.label.value for r in rows)
    setups = Counter(r.setup_state for r in rows)
    splits = Counter((r.split or "unassigned") for r in rows)
    missing_features = 0
    unknown_features = 0
    for r in rows:
        for payload in r.features.values():
            if not isinstance(payload, dict):
                missing_features += 1
                continue
            if payload.get("status") == "unknown":
                unknown_features += 1
    winners = labels.get(LabelClass.WIN.value, 0)
    losers = labels.get(LabelClass.LOSS.value, 0)
    waits = labels.get(LabelClass.WAIT.value, 0)
    no_setups = labels.get(LabelClass.NO_SETUP.value, 0)
    return {
        "row_count": len(rows),
        "label_counts": dict(labels),
        "setup_state_counts": dict(setups),
        "split_counts": dict(splits),
        "includes_non_winners": (losers + waits + no_setups) > 0,
        "unknown_feature_observations": unknown_features,
        "traceability": {
            "all_rows_have_source_timestamp": all(r.source_bar_open_time is not None for r in rows),
            "all_rows_have_strategy_version": all(
                r.strategy_code and r.strategy_version_no is not None for r in rows
            ),
            "all_rows_have_label_policy": all(
                r.label_policy_id and r.label_policy_version for r in rows
            ),
        },
        "class_balance_note": {
            "win": winners,
            "loss": losers,
            "wait": waits,
            "no_setup": no_setups,
        },
    }
