"""Versioned strategy engine."""

from private_trading_strategies.challenger import SOL_MTF_CHALLENGER_V1, ChallengerSpec
from private_trading_strategies.context import DEFAULT_ENTRY_PATH, build_playbook_context
from private_trading_strategies.evaluate import (
    STRATEGY_ENGINE_VERSION,
    StrategyDefinition,
    evaluate_strategy,
)
from private_trading_strategies.types import (
    Direction,
    FeatureFact,
    RuleResult,
    SetupState,
    StrategyAssessment,
)
from private_trading_strategies.wyckoff_hdm import build_wyckoff_hdm_v1

__all__ = [
    "DEFAULT_ENTRY_PATH",
    "SOL_MTF_CHALLENGER_V1",
    "STRATEGY_ENGINE_VERSION",
    "ChallengerSpec",
    "Direction",
    "FeatureFact",
    "RuleResult",
    "SetupState",
    "StrategyAssessment",
    "StrategyDefinition",
    "build_playbook_context",
    "build_wyckoff_hdm_v1",
    "evaluate_strategy",
]
__version__ = STRATEGY_ENGINE_VERSION
