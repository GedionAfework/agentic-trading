from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from private_trading_ai_gateway.client import AIGatewayError
from private_trading_core.config import get_settings, production_settings_errors
from private_trading_core.ids import new_correlation_id
from private_trading_core.logging import configure_logging, get_logger
from private_trading_db.session import dispose_engine

from private_trading_api.errors import register_exception_handlers
from private_trading_api.metrics import REGISTRY
from private_trading_api.rate_limit import client_key, limiter
from private_trading_api.routes.ai import router as ai_router
from private_trading_api.routes.analytics import router as analytics_router
from private_trading_api.routes.auth import router as auth_router
from private_trading_api.routes.backtests import router as backtests_router
from private_trading_api.routes.decision import router as decision_router
from private_trading_api.routes.decisions import router as decisions_router
from private_trading_api.routes.health import router as health_router
from private_trading_api.routes.knowledge import router as knowledge_router
from private_trading_api.routes.markets import router as markets_router
from private_trading_api.routes.ops import router as ops_router
from private_trading_api.routes.paper import router as paper_router
from private_trading_api.routes.release import router as release_router
from private_trading_api.routes.risk import router as risk_router
from private_trading_api.routes.scanner import router as scanner_router
from private_trading_api.routes.strategies import router as strategies_router
from private_trading_api.routes.telegram import router as telegram_router
from private_trading_api.routes.training import router as training_router
from private_trading_api.routes.vision import router as vision_router

logger = get_logger(__name__)

_AUTH_PATHS = {"/v1/auth/login", "/auth/login"}
_UPLOAD_HINTS = ("/vision/screenshots", "/knowledge/documents")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    errors = production_settings_errors(settings)
    if errors:
        logger.error("production_settings_blocked errors=%s", errors)
        raise SystemExit("Refusing to start: " + "; ".join(errors))
    logger.info("api_starting env=%s", settings.app_env)
    yield
    await dispose_engine()
    logger.info("api_stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def security_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
        request.state.correlation_id = correlation_id
        settings = get_settings()

        # Reject oversized bodies early when Content-Length is present.
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            size = int(content_length)
            if size > settings.max_upload_bytes and any(
                hint in request.url.path for hint in _UPLOAD_HINTS
            ):
                REGISTRY.inc(
                    "pta_http_requests_total",
                    labels={"path": "upload", "status": "413"},
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "UPLOAD_TOO_LARGE",
                            "message": f"Body exceeds {settings.max_upload_bytes} bytes",
                            "correlation_id": correlation_id,
                            "retryable": False,
                        }
                    },
                    headers={"X-Correlation-ID": correlation_id},
                )

        if settings.rate_limit_enabled and request.url.path not in {
            "/health",
            "/v1/health",
            "/metrics",
            "/v1/metrics",
        }:
            host = request.client.host if request.client else None
            path = request.url.path
            if path in _AUTH_PATHS:
                limit = settings.rate_limit_auth_requests
                bucket = "auth"
            elif any(hint in path for hint in _UPLOAD_HINTS):
                limit = settings.rate_limit_upload_requests
                bucket = "upload"
            else:
                limit = settings.rate_limit_requests
                bucket = "api"
            allowed, retry_after = limiter.allow(
                client_key(host, path if bucket != "api" else bucket, bucket),
                limit=limit,
                window_seconds=float(settings.rate_limit_window_seconds),
            )
            if not allowed:
                REGISTRY.inc(
                    "pta_http_requests_total",
                    labels={"path": bucket, "status": "429"},
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "Too many requests",
                            "correlation_id": correlation_id,
                            "retryable": True,
                        }
                    },
                    headers={
                        "X-Correlation-ID": correlation_id,
                        "Retry-After": str(retry_after),
                    },
                )

        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        response.headers["X-Correlation-ID"] = correlation_id
        route_label = request.url.path.split("?")[0]
        if len(route_label) > 64:
            route_label = route_label[:64]
        REGISTRY.inc(
            "pta_http_requests_total",
            labels={"path": route_label, "status": str(response.status_code)},
        )
        REGISTRY.observe(
            "pta_http_request_duration_seconds",
            elapsed,
            labels={"path": route_label},
        )
        return response

    register_exception_handlers(app)

    @app.exception_handler(AIGatewayError)
    async def ai_gateway_error_handler(request, exc: AIGatewayError):
        status_code = 503 if exc.retryable else 502
        correlation_id = getattr(request.state, "correlation_id", None)
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "correlation_id": correlation_id,
                    "retryable": exc.retryable,
                    "details": exc.details,
                }
            },
        )

    app.include_router(health_router)
    app.include_router(health_router, prefix="/v1")
    app.include_router(ops_router)
    app.include_router(ops_router, prefix="/v1")
    app.include_router(auth_router, prefix="/v1")
    app.include_router(ai_router, prefix="/v1")
    app.include_router(knowledge_router, prefix="/v1")
    app.include_router(markets_router, prefix="/v1")
    app.include_router(strategies_router, prefix="/v1")
    app.include_router(risk_router, prefix="/v1")
    app.include_router(backtests_router, prefix="/v1")
    app.include_router(training_router, prefix="/v1")
    app.include_router(decision_router, prefix="/v1")
    app.include_router(decisions_router, prefix="/v1")
    app.include_router(vision_router, prefix="/v1")
    app.include_router(scanner_router, prefix="/v1")
    app.include_router(telegram_router, prefix="/v1")
    app.include_router(paper_router, prefix="/v1")
    app.include_router(analytics_router, prefix="/v1")
    app.include_router(release_router, prefix="/v1")
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "private_trading_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=get_settings().app_env == "development",
    )
