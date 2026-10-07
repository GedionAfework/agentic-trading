from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from private_trading_decision.matrix import VECTOR_NAMES, encode_features


@dataclass(slots=True)
class RankDecision:
    recommendation: str
    reason: str
    score: float | None
    band: str
    abstained: bool
    gates_passed: bool
    mode: str
    hard_blockers: list[str] = field(default_factory=list)
    score_kind: str = "model_rank_score"
    not_a_calibrated_probability: bool = True
    llm_may_invent_probability: bool = False
    cannot_bypass_strategy_or_risk: bool = True


def qualitative_band(score: float | None, *, threshold: float) -> tuple[str, bool]:
    if score is None or score < threshold:
        return "abstain", True
    if score < 0.65:
        return "low", False
    if score < 0.8:
        return "medium", False
    return "high", False


def apply_gates(
    *,
    score: float | None,
    threshold: float,
    strategy_ready: bool,
    risk_approved: bool,
    hard_blockers: list[str] | None = None,
    mode: str = "shadow",
) -> RankDecision:
    """Strategy and risk remain the authority. The model only ranks when both pass."""
    supplied = [b for b in (hard_blockers or []) if b]
    blockers = list(supplied)
    if not strategy_ready and "strategy_not_ready" not in blockers:
        blockers.append("strategy_not_ready")
    if not risk_approved and "risk_veto" not in blockers:
        blockers.append("risk_veto")
    gates_passed = strategy_ready and risk_approved and not supplied
    band, abstained = qualitative_band(score, threshold=threshold)

    if not gates_passed:
        return RankDecision(
            recommendation="WAIT",
            reason="strategy_or_risk_veto",
            score=score,
            band=band,
            abstained=abstained,
            gates_passed=False,
            mode=mode,
            hard_blockers=blockers,
        )
    if mode == "shadow":
        return RankDecision(
            recommendation="ENTER",
            reason="gates_passed_shadow_score_informational",
            score=score,
            band=band,
            abstained=abstained,
            gates_passed=True,
            mode=mode,
        )
    if abstained or band in {"abstain", "low"}:
        return RankDecision(
            recommendation="WAIT",
            reason="model_abstain",
            score=score,
            band=band,
            abstained=True,
            gates_passed=True,
            mode=mode,
        )
    return RankDecision(
        recommendation="ENTER",
        reason="gates_passed_and_rank_band",
        score=score,
        band=band,
        abstained=False,
        gates_passed=True,
        mode=mode,
    )


def _sigmoid(value: float) -> float:
    if value > 30:
        return 1.0
    if value < -30:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


class LoadedModel:
    def __init__(self, artifact: dict[str, Any]) -> None:
        self.artifact = artifact
        self.kind = str(artifact.get("kind"))
        self.threshold = float(artifact.get("abstention_threshold", 0.55))
        names = list(artifact.get("feature_names") or [])
        if names and names != list(VECTOR_NAMES):
            raise ValueError("artifact feature order does not match the feature schema")

    def score(self, features: dict[str, Any]) -> float | None:
        if self.kind != "logistic_ranker":
            return None
        weights = [float(w) for w in self.artifact["weights"]]
        bias = float(self.artifact["bias"])
        vector = encode_features(features)
        raw = bias + sum(w * x for w, x in zip(weights, vector, strict=True))
        return _sigmoid(raw)

    def decide(
        self,
        features: dict[str, Any],
        *,
        strategy_ready: bool,
        risk_approved: bool,
        hard_blockers: list[str] | None = None,
        mode: str = "shadow",
    ) -> RankDecision:
        return apply_gates(
            score=self.score(features),
            threshold=self.threshold,
            strategy_ready=strategy_ready,
            risk_approved=risk_approved,
            hard_blockers=hard_blockers,
            mode=mode,
        )
