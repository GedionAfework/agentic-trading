"""Decision ML — Phase 10 training dataset builder (inference in Phase 11)."""

from private_trading_decision.builder import DATASET_BUILDER_VERSION, build_training_dataset
from private_trading_decision.types import LabelClass, LabelPolicy, TrainingRow

__all__ = [
    "DATASET_BUILDER_VERSION",
    "LabelClass",
    "LabelPolicy",
    "TrainingRow",
    "build_training_dataset",
]
__version__ = DATASET_BUILDER_VERSION
