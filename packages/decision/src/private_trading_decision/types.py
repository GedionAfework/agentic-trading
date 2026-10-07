from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class LabelClass(StrEnum):
    """Include WAIT/NO_SETUP and losers — not only winners."""

    WIN = "win"
    LOSS = "loss"
    WAIT = "wait"
    NO_SETUP = "no_setup"
    SKIPPED = "skipped"  # insufficient forward horizon / incomplete


class SplitName(StrEnum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"


@dataclass(slots=True, frozen=True)
class LabelPolicy:
    """Pinned labeling assumptions — shared with backtest cost/fill semantics."""

    policy_id: str = "label.v1"
    version: str = "1.0.0"
    horizon_bars: int = 12
    fill_policy: str = "next_open"
    same_candle_ambiguity: str = "conservative"
    fee_bps: str = "10"
    slippage_bps: str = "5"
    spread_bps: str = "2"
    min_rr: str = "2.0"
    direction: str = "long"
    outcome_source: str = "backtest"
    strategy_code: str = "wyckoff-hdm"
    strategy_version_no: int = 1
    advisory_definitions: tuple[str, ...] = ("WYK-001", "IMB-001", "SMT-001")

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "horizon_bars": self.horizon_bars,
            "fill_policy": self.fill_policy,
            "same_candle_ambiguity": self.same_candle_ambiguity,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "spread_bps": self.spread_bps,
            "min_rr": self.min_rr,
            "direction": self.direction,
            "outcome_source": self.outcome_source,
            "strategy_code": self.strategy_code,
            "strategy_version_no": self.strategy_version_no,
            "advisory_definitions": list(self.advisory_definitions),
        }


@dataclass(slots=True)
class TrainingRow:
    row_id: str
    bar_index: int
    open_time: datetime
    symbol: str
    timeframe: str
    features: dict[str, Any]
    feature_versions: dict[str, str]
    setup_state: str
    direction: str
    label: LabelClass
    pnl_r: Decimal | None
    exit_reason: str | None
    entry_bar_index: int | None
    exit_bar_index: int | None
    strategy_code: str
    strategy_version_no: int
    label_policy_id: str
    label_policy_version: str
    outcome_source: str
    source_bar_open_time: datetime  # raw timestamp trace
    split: str | None = None
    fold_id: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DatasetBuildResult:
    rows: list[TrainingRow]
    fingerprint: str
    feature_schema: dict[str, Any]
    split_manifest: dict[str, Any]
    quality_report: dict[str, Any]
    engine_versions: dict[str, Any]
    label_policy: dict[str, Any]
    source_dataset_fingerprint: str
