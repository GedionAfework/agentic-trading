"""Decision ML — dataset builder (Phase 10) and ranker (Phase 11)."""

from private_trading_decision.builder import DATASET_BUILDER_VERSION, build_training_dataset
from private_trading_decision.matrix import DECISION_MODEL_VERSION
from private_trading_decision.predict import apply_gates
from private_trading_decision.train import train_baseline_and_challenger
from private_trading_decision.types import LabelClass, LabelPolicy, TrainingRow

__all__ = [
    "DATASET_BUILDER_VERSION",
    "DECISION_MODEL_VERSION",
    "LabelClass",
    "LabelPolicy",
    "TrainingRow",
    "apply_gates",
    "build_training_dataset",
    "train_baseline_and_challenger",
]
__version__ = DECISION_MODEL_VERSION
