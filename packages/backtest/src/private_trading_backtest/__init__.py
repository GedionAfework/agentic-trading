"""Historical replay engine — same evaluators as live; no look-ahead fills."""

from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.fixtures import frozen_bos_long_fixture
from private_trading_backtest.replay import BACKTEST_ENGINE_VERSION, run_replay
from private_trading_backtest.types import BacktestReport, OutcomeSource
from private_trading_backtest.walkforward import (
    PAIR_COST_BPS,
    ResearchObjective,
    ResearchPerformance,
    SelectionPolicy,
    TimeFold,
    pair_cost_bps,
    run_walk_forward,
)

__all__ = [
    "BACKTEST_ENGINE_VERSION",
    "BacktestReport",
    "OutcomeSource",
    "PAIR_COST_BPS",
    "ResearchObjective",
    "ResearchPerformance",
    "SelectionPolicy",
    "TimeFold",
    "dataset_fingerprint",
    "frozen_bos_long_fixture",
    "pair_cost_bps",
    "run_replay",
    "run_walk_forward",
]
__version__ = BACKTEST_ENGINE_VERSION
