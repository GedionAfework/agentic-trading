"""Celery application stub — queues wired in later phases."""

from private_trading_core.config import get_settings

try:
    from celery import Celery
except ImportError:  # pragma: no cover
    Celery = None  # type: ignore[misc, assignment]


def create_celery_app():
    if Celery is None:
        raise RuntimeError("celery is not installed yet; add it when implementing workers")
    settings = get_settings()
    app = Celery("private_trading", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.task_default_queue = "default"
    return app
