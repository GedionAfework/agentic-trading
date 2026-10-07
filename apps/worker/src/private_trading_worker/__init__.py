"""Celery worker entrypoint.

Run:
  uv run celery -A private_trading_worker.celery_app:celery_app worker -B \
    -Q market,ai,notifications,backtests
Fallback without a broker: `uv run python -m private_trading_worker`
"""

from private_trading_worker.celery_app import celery_app, create_celery_app, run_scanner_loop

__all__ = ["celery_app", "create_celery_app", "run_scanner_loop"]
__version__ = "0.1.0"
