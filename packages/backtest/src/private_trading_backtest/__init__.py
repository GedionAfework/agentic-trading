"""Historical replay engine — same evaluators as live; no look-ahead fills."""

from private_trading_backtest.fingerprint import dataset_fingerprint
from private_trading_backtest.fixtures import frozen_bos_long_fixture
from private_trading_backtest.replay import BACKTEST_ENGINE_VERSION, run_replay
from private_trading_backtest.types import BacktestReport, OutcomeSource

__all__ = [
    "BACKTEST_ENGINE_VERSION",
    "BacktestReport",
    "OutcomeSource",
    "dataset_fingerprint",
    "frozen_bos_long_fixture",
    "run_replay",
]
__version__ = BACKTEST_ENGINE_VERSION
