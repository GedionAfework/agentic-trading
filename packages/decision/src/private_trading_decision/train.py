from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

from private_trading_decision.labels import feature_schema
from private_trading_decision.matrix import (
    DECISION_MODEL_VERSION,
    VECTOR_NAMES,
    encode_features,
    is_positive,
)
from private_trading_decision.types import TrainingRow

# Two fixed candidates. The abstention threshold and the winner are chosen on validation only.
BASELINE_PARAMS: dict[str, Any] = {"learning_rate": 0.05, "epochs": 80, "l2": 0.01}
CHALLENGER_PARAMS: dict[str, Any] = {"learning_rate": 0.12, "epochs": 140, "l2": 0.001}
_THRESHOLDS = [round(0.35 + i * 0.05, 2) for i in range(10)]


@dataclass(slots=True)
class TrainedCandidate:
    role: str
    algorithm: str
    params: dict[str, Any]
    artifact: dict[str, Any]
    metrics: dict[str, Any]
    feature_importance: list[dict[str, Any]]
    training_window: dict[str, Any]
    feature_schema: dict[str, Any]
    fingerprint: str
    selected_on: str = "val"


@dataclass(slots=True)
class TrainResult:
    baseline: TrainedCandidate
    challenger: TrainedCandidate
    recommended_role: str
    notes: list[str] = field(default_factory=list)


def _split(rows: list[TrainingRow], name: str) -> list[TrainingRow]:
    tagged = [r for r in rows if r.split == name]
    return tagged if tagged else []


def _xy(rows: list[TrainingRow]) -> tuple[list[list[float]], list[int]]:
    return [encode_features(r.features) for r in rows], [is_positive(r) for r in rows]


def _window(rows: list[TrainingRow]) -> dict[str, Any]:
    if not rows:
        return {"start": None, "end": None, "row_count": 0}
    ordered = sorted(rows, key=lambda r: r.open_time)
    return {
        "start": ordered[0].open_time.isoformat(),
        "end": ordered[-1].open_time.isoformat(),
        "row_count": len(rows),
        "symbol": ordered[0].symbol,
        "timeframe": ordered[0].timeframe,
    }


def _sigmoid(value: float) -> float:
    if value > 30:
        return 1.0
    if value < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def _dot(weights: list[float], bias: float, row: list[float]) -> float:
    return bias + sum(w * x for w, x in zip(weights, row, strict=True))


def _fit(
    x: list[list[float]], y: list[int], params: dict[str, Any]
) -> tuple[list[float], float] | None:
    if len(y) < 2 or len(set(y)) < 2:
        return None
    width = len(VECTOR_NAMES)
    weights = [0.0] * width
    bias = 0.0
    lr = float(params["learning_rate"])
    l2 = float(params["l2"])
    for _ in range(int(params["epochs"])):
        for row, target in zip(x, y, strict=True):
            error = _sigmoid(_dot(weights, bias, row)) - target
            for j in range(width):
                weights[j] -= lr * (error * row[j] + l2 * weights[j])
            bias -= lr * error
    return weights, bias


def _scores(model: tuple[list[float], float] | None, x: list[list[float]]) -> list[float]:
    if not x:
        return []
    if model is None:
        return [0.0] * len(x)
    weights, bias = model
    return [_sigmoid(_dot(weights, bias, row)) for row in x]


def _binary_metrics(y: list[int], scores: list[float], threshold: float) -> dict[str, Any]:
    if not y:
        return {"row_count": 0, "note": "empty_split"}
    pred = [1 if score >= threshold else 0 for score in scores]
    correct = sum(int(p == t) for p, t in zip(pred, y, strict=True))
    positives = sum(y)
    out: dict[str, Any] = {
        "row_count": len(y),
        "positive_count": positives,
        "accuracy": correct / len(y),
        "threshold": threshold,
        "mean_score": sum(scores) / len(scores),
    }
    if positives == 0 or positives == len(y):
        out["auc"] = None
        out["auc_note"] = "single_class_split"
        return out
    pos = [s for s, t in zip(scores, y, strict=True) if t == 1]
    neg = [s for s, t in zip(scores, y, strict=True) if t == 0]
    wins = 0.0
    for p in pos:
        wins += sum(1.0 for n in neg if n < p) + 0.5 * sum(1.0 for n in neg if n == p)
    out["auc"] = wins / (len(pos) * len(neg))
    return out


def _best_threshold(y: list[int], scores: list[float]) -> tuple[float, str]:
    if not y or sum(y) == 0 or sum(y) == len(y):
        return 0.55, "default_insufficient_validation_classes"
    best_t = 0.55
    best_acc = -1.0
    for threshold in _THRESHOLDS:
        acc = sum(int((score >= threshold) == target) for score, target in zip(scores, y, strict=True))
        acc /= len(y)
        if acc > best_acc:
            best_acc = acc
            best_t = float(threshold)
    return best_t, "validation_accuracy"


def _candidate(
    *,
    role: str,
    params: dict[str, Any],
    train_rows: list[TrainingRow],
    val_rows: list[TrainingRow],
    test_rows: list[TrainingRow],
) -> TrainedCandidate:
    x_train, y_train = _xy(train_rows)
    x_val, y_val = _xy(val_rows)
    x_test, y_test = _xy(test_rows)
    fitted = _fit(x_train, y_train, params)
    val_scores = _scores(fitted, x_val)
    threshold, threshold_source = _best_threshold(y_val, val_scores)
    if fitted is None:
        artifact: dict[str, Any] = {
            "kind": "constant_abstain",
            "reason": "training_split_lacks_both_classes",
            "feature_names": list(VECTOR_NAMES),
            "abstention_threshold": threshold,
            "engine_version": DECISION_MODEL_VERSION,
        }
        importance: list[dict[str, Any]] = []
        algorithm = "constant_abstain"
    else:
        weights, bias = fitted
        importance = [
            {"name": VECTOR_NAMES[i], "gain": abs(weights[i])}
            for i in range(len(VECTOR_NAMES))
            if abs(weights[i]) > 0
        ]
        importance.sort(key=lambda item: item["gain"], reverse=True)
        artifact = {
            "kind": "logistic_ranker",
            "weights": weights,
            "bias": bias,
            "feature_names": list(VECTOR_NAMES),
            "abstention_threshold": threshold,
            "engine_version": DECISION_MODEL_VERSION,
            "score_kind": "model_rank_score",
            "not_a_calibrated_probability": True,
        }
        algorithm = "logistic_ranker"
    metrics = {
        "selection_split": "val",
        "threshold_source": threshold_source,
        "abstention_threshold": threshold,
        "train": _binary_metrics(y_train, _scores(fitted, x_train), threshold),
        "val": _binary_metrics(y_val, val_scores, threshold),
        "test": _binary_metrics(y_test, _scores(fitted, x_test), threshold),
        "notes": [
            "Test split was not used to choose hyperparameters or the abstention threshold.",
            "Numeric score is a rank score. Qualitative bands are the display contract.",
            "LLM must not invent or restate this score as a probability.",
        ],
    }
    raw = json.dumps(
        {"role": role, "params": params, "artifact": artifact, "metrics": metrics},
        sort_keys=True,
        default=str,
    )
    return TrainedCandidate(
        role=role,
        algorithm=algorithm,
        params=params,
        artifact=artifact,
        metrics=metrics,
        feature_importance=importance,
        training_window=_window(train_rows),
        feature_schema=feature_schema(),
        fingerprint=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def train_baseline_and_challenger(rows: list[TrainingRow]) -> TrainResult:
    baseline = _candidate(
        role="baseline",
        params=BASELINE_PARAMS,
        train_rows=_split(rows, "train"),
        val_rows=_split(rows, "val"),
        test_rows=_split(rows, "test"),
    )
    challenger = _candidate(
        role="challenger",
        params=CHALLENGER_PARAMS,
        train_rows=_split(rows, "train"),
        val_rows=_split(rows, "val"),
        test_rows=_split(rows, "test"),
    )
    base_acc = baseline.metrics["val"].get("accuracy")
    chal_acc = challenger.metrics["val"].get("accuracy")
    if chal_acc is None or (base_acc is not None and base_acc >= chal_acc):
        recommended = "baseline"
    else:
        recommended = "challenger"
    return TrainResult(
        baseline=baseline,
        challenger=challenger,
        recommended_role=recommended,
        notes=[
            "Both models stay in shadow until an explicit promote call.",
            "Promotion does not let the model override strategy or risk gates.",
        ],
    )
