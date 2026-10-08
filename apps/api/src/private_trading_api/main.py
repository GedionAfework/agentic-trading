from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from private_trading_ai_gateway.client import AIGatewayError
from private_trading_core.config import get_settings
from private_trading_core.ids import new_correlation_id
from private_trading_core.logging import configure_logging, get_logger
from private_trading_db.session import dispose_engine

from private_trading_api.errors import register_exception_handlers
from private_trading_api.routes.ai import router as ai_router
from private_trading_api.routes.auth import router as auth_router
from private_trading_api.routes.backtests import router as backtests_router
from private_trading_api.routes.decision import router as decision_router
from private_trading_api.routes.decisions import router as decisions_router
from private_trading_api.routes.health import router as health_router
from private_trading_api.routes.knowledge import router as knowledge_router
from private_trading_api.routes.markets import router as markets_router
from private_trading_api.routes.paper import router as paper_router
from private_trading_api.routes.risk import router as risk_router
from private_trading_api.routes.scanner import router as scanner_router
from private_trading_api.routes.strategies import router as strategies_router
from private_trading_api.routes.telegram import router as telegram_router
from private_trading_api.routes.training import router as training_router
from private_trading_api.routes.vision import router as vision_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
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
    async def correlation_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    register_exception_handlers(app)

    @app.exception_handler(AIGatewayError)
    async def ai_gateway_error_handler(request, exc: AIGatewayError):
        from fastapi.responses import JSONResponse

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
