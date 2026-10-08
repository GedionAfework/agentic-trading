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
from private_trading_paper_trade.service import (
    accept_decision,
    account_summary,
    cancel_trade,
    ensure_paper_account,
    get_trade,
    list_events,
    list_trades,
    monitor_account,
)

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
    "__version__",
]
