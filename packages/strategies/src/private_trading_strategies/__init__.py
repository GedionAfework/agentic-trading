"""Versioned strategy engine."""

from private_trading_strategies.challenger import (
    SOL_MTF_CHALLENGER_V1,
    SOL_MTF_CHALLENGER_V2_SCALE_OUT,
    SOL_MTF_CHALLENGER_V3_DAILY4H,
    STEP6_CATALOG_VERSION,
    ChallengerSpec,
)
from private_trading_strategies.context import DEFAULT_ENTRY_PATH, build_playbook_context
from private_trading_strategies.evaluate import (
    STRATEGY_ENGINE_VERSION,
    StrategyDefinition,
    evaluate_strategy,
)
from private_trading_strategies.multi_market import (
    DOGE_PROFIT_MODEL,
    PAPER_MODEL_REGISTRY,
    SOL_PROFIT_MODEL,
    SOL_WIN_RATE_MODEL,
    MarketModelSpec,
    MarketRegime,
    TradingObjective,
    classify_market_regime,
    resolve_market_model,
)
from private_trading_strategies.soak_freeze import (
    SOAK_FREEZE_ID,
    SOAK_OBJECTIVE,
    SOAK_SYMBOL,
    assert_soak_freeze,
    owner_test_symbols,
    soak_incumbent,
    soak_scan_symbols,
    soak_scan_timeframes,
)
from private_trading_strategies.specialist_catalog import (
    SPECIALIST_CATALOG_VERSION,
    specialist_candidates,
)
from private_trading_strategies.specialist_registry import (
    VALIDATED_SPECIALIST_MODELS,
    ValidatedSpecialistModel,
    resolve_specialist_model,
)
from private_trading_strategies.specialists import (
    SPECIALIST_FAMILIES_BY_SYMBOL,
    SpecialistAction,
    SpecialistConfig,
    SpecialistContext,
    SpecialistSignal,
    StrategyFamily,
    evaluate_specialist,
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
    "SOL_MTF_CHALLENGER_V2_SCALE_OUT",
    "SOL_MTF_CHALLENGER_V3_DAILY4H",
    "STEP6_CATALOG_VERSION",
    "STRATEGY_ENGINE_VERSION",
    "ChallengerSpec",
    "Direction",
    "FeatureFact",
    "MarketModelSpec",
    "MarketRegime",
    "DOGE_PROFIT_MODEL",
    "PAPER_MODEL_REGISTRY",
    "RuleResult",
    "SOAK_FREEZE_ID",
    "SOAK_OBJECTIVE",
    "SOAK_SYMBOL",
    "SOL_PROFIT_MODEL",
    "SOL_WIN_RATE_MODEL",
    "owner_test_symbols",
    "SPECIALIST_FAMILIES_BY_SYMBOL",
    "SPECIALIST_CATALOG_VERSION",
    "SetupState",
    "SpecialistAction",
    "SpecialistConfig",
    "SpecialistContext",
    "SpecialistSignal",
    "StrategyFamily",
    "StrategyAssessment",
    "StrategyDefinition",
    "TradingObjective",
    "VALIDATED_SPECIALIST_MODELS",
    "ValidatedSpecialistModel",
    "build_playbook_context",
    "build_wyckoff_hdm_v1",
    "classify_market_regime",
    "evaluate_strategy",
    "assert_soak_freeze",
    "evaluate_specialist",
    "resolve_market_model",
    "soak_incumbent",
    "soak_scan_symbols",
    "soak_scan_timeframes",
    "resolve_specialist_model",
    "specialist_candidates",
]
__version__ = STRATEGY_ENGINE_VERSION
