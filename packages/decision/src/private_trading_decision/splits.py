from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from private_trading_decision.types import SplitName, TrainingRow


@dataclass(slots=True, frozen=True)
class TimeSplitConfig:
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15

    def __post_init__(self) -> None:
        total = self.train_ratio + self.val_ratio + self.test_ratio
        if abs(total - 1.0) > 1e-6:
            raise ValueError("split ratios must sum to 1.0")


@dataclass(slots=True, frozen=True)
class WalkForwardConfig:
    n_folds: int = 3
    embargo_bars: int = 0  # gap between train end and test start


def assign_time_splits(
    rows: list[TrainingRow],
    *,
    config: TimeSplitConfig | None = None,
) -> tuple[list[TrainingRow], dict]:
    """Pure time-ordered split — never shuffle (leakage-safe)."""
    cfg = config or TimeSplitConfig()
    ordered = sorted(rows, key=lambda r: (r.open_time, r.bar_index))
    n = len(ordered)
    if n == 0:
        return [], {"mode": "time", "counts": {}, "boundaries": {}}

    train_end = int(n * cfg.train_ratio)
    val_end = train_end + int(n * cfg.val_ratio)
    # Ensure test gets the remainder
    boundaries = {
        "train": [0, max(train_end, 0)],
        "val": [max(train_end, 0), max(val_end, train_end)],
        "test": [max(val_end, train_end), n],
    }
    # Fix empty edge cases on tiny n
    if n >= 3 and boundaries["train"][1] == 0:
        boundaries["train"] = [0, 1]
        boundaries["val"] = [1, 2]
        boundaries["test"] = [2, n]
    elif n == 2:
        boundaries = {"train": [0, 1], "val": [1, 1], "test": [1, 2]}
    elif n == 1:
        boundaries = {"train": [0, 1], "val": [1, 1], "test": [1, 1]}

    for i, row in enumerate(ordered):
        if boundaries["train"][0] <= i < boundaries["train"][1]:
            row.split = SplitName.TRAIN.value
        elif boundaries["val"][0] <= i < boundaries["val"][1]:
            row.split = SplitName.VAL.value
        else:
            row.split = SplitName.TEST.value
        row.fold_id = None

    counts = {
        "train": sum(1 for r in ordered if r.split == "train"),
        "val": sum(1 for r in ordered if r.split == "val"),
        "test": sum(1 for r in ordered if r.split == "test"),
    }
    times = {
        name: {
            "start": ordered[lo].open_time.isoformat() if lo < n and lo < hi else None,
            "end": ordered[hi - 1].open_time.isoformat() if hi > lo else None,
        }
        for name, (lo, hi) in boundaries.items()
    }
    return ordered, {
        "mode": "time",
        "ratios": {
            "train_ratio": cfg.train_ratio,
            "val_ratio": cfg.val_ratio,
            "test_ratio": cfg.test_ratio,
        },
        "counts": counts,
        "boundaries_index": boundaries,
        "boundaries_time": times,
    }


def assign_walk_forward(
    rows: list[TrainingRow],
    *,
    config: WalkForwardConfig | None = None,
) -> tuple[list[TrainingRow], dict]:
    """Expanding-window walk-forward folds on time-ordered rows."""
    cfg = config or WalkForwardConfig()
    ordered = sorted(rows, key=lambda r: (r.open_time, r.bar_index))
    n = len(ordered)
    folds: list[dict] = []
    if n == 0 or cfg.n_folds < 1:
        return ordered, {"mode": "walk_forward", "folds": [], "counts": {}}

    # Split timeline into fold segments for test windows
    fold_size = max(n // (cfg.n_folds + 1), 1)
    for fold_id in range(cfg.n_folds):
        test_start = fold_size * (fold_id + 1)
        test_end = min(n, test_start + fold_size) if fold_id < cfg.n_folds - 1 else n
        train_end = max(0, test_start - cfg.embargo_bars)
        if train_end <= 0 or test_start >= n:
            continue
        folds.append(
            {
                "fold_id": fold_id,
                "train_index": [0, train_end],
                "test_index": [test_start, test_end],
                "train_time": {
                    "start": ordered[0].open_time.isoformat(),
                    "end": ordered[train_end - 1].open_time.isoformat(),
                },
                "test_time": {
                    "start": ordered[test_start].open_time.isoformat()
                    if test_start < n
                    else None,
                    "end": ordered[test_end - 1].open_time.isoformat()
                    if test_end > test_start
                    else None,
                },
            }
        )

    # Primary split tags use fold 0 mapping + overall time split leftover as val unused
    # Tag each row with fold membership for fold 0 train/test; other folds in manifest only
    # Also set split=train/test based on last fold for a simple default export
    if folds:
        last = folds[-1]
        tr0, tr1 = last["train_index"]
        te0, te1 = last["test_index"]
        for i, row in enumerate(ordered):
            row.fold_id = None
            if tr0 <= i < tr1:
                row.split = SplitName.TRAIN.value
                row.fold_id = last["fold_id"]
            elif te0 <= i < te1:
                row.split = SplitName.TEST.value
                row.fold_id = last["fold_id"]
            else:
                row.split = SplitName.VAL.value

    counts = {
        "train": sum(1 for r in ordered if r.split == "train"),
        "val": sum(1 for r in ordered if r.split == "val"),
        "test": sum(1 for r in ordered if r.split == "test"),
    }
    return ordered, {
        "mode": "walk_forward",
        "n_folds": cfg.n_folds,
        "embargo_bars": cfg.embargo_bars,
        "folds": folds,
        "counts": counts,
        "note": "row.split reflects final fold train/test; all folds listed in folds[]",
    }


def assert_no_time_leakage(rows: Iterable[TrainingRow]) -> None:
    """Train timestamps must not overlap test timestamps when both assigned."""
    train_times = [r.open_time for r in rows if r.split == SplitName.TRAIN.value]
    test_times = [r.open_time for r in rows if r.split == SplitName.TEST.value]
    if not train_times or not test_times:
        return
    if max(train_times) >= min(test_times):
        raise ValueError("time leakage: train max timestamp >= test min timestamp")
