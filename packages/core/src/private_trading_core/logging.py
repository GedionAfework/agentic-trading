from __future__ import annotations

import logging
import sys
from typing import Any

from private_trading_core.config import get_settings


class CorrelationFilter(logging.Filter):
    """Ensure every log record has a correlation_id attribute."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = "-"  # type: ignore[attr-defined]
        return True


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt=(
                "%(asctime)s %(levelname)s service=%(name)s "
                "correlation_id=%(correlation_id)s %(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(CorrelationFilter())

    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def get_logger(name: str, **extra: Any) -> logging.LoggerAdapter[logging.Logger]:
    logger = logging.getLogger(name)
    return logging.LoggerAdapter(logger, extra)
