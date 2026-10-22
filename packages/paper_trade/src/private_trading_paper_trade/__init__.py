"""Paper trading simulation — forward validation without live money."""

from private_trading_paper_trade.engine import (
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_READY,
    PaperPlan,
    evaluate_exit_on_bar,
    try_fill_at_next_open,
    validate_plan,
)
from private_trading_paper_trade.fill_model import (
    PAPER_ENGINE_VERSION,
    PAPER_LABEL,
    default_fill_model,
)
from private_trading_paper_trade.holdout import evaluate_holdout_review
from private_trading_paper_trade.live_alert_gate import evaluate_live_alert_decision
from private_trading_paper_trade.promotion import evaluate_paper_promotion
from private_trading_paper_trade.service import (
    accept_decision,
    account_summary,
    cancel_trade,
    ensure_paper_account,
    get_trade,
    list_events,
    list_trades,
    monitor_account,
    soak_step1_progress,
    soak_step2_progress,
    soak_step3_progress,
    soak_step4_progress,
    soak_step5_progress,
)
from private_trading_paper_trade.soak_metrics import evaluate_soak_sample

__version__ = "0.1.0"

__all__ = [
    "STATUS_CANCELLED",
    "STATUS_CLOSED",
    "STATUS_OPEN",
    "STATUS_READY",
    "PaperPlan",
    "evaluate_exit_on_bar",
    "try_fill_at_next_open",
    "validate_plan",
    "PAPER_ENGINE_VERSION",
    "PAPER_LABEL",
    "default_fill_model",
    "accept_decision",
    "account_summary",
    "cancel_trade",
    "ensure_paper_account",
    "get_trade",
    "list_events",
    "list_trades",
    "monitor_account",
    "soak_step1_progress",
    "soak_step2_progress",
    "soak_step3_progress",
    "soak_step4_progress",
    "soak_step5_progress",
    "evaluate_holdout_review",
    "evaluate_live_alert_decision",
    "evaluate_paper_promotion",
    "evaluate_soak_sample",
    "__version__",
]
