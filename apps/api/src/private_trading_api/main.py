from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from private_trading_core.config import get_settings
from private_trading_core.ids import new_correlation_id
from private_trading_core.logging import configure_logging, get_logger

from private_trading_api.routes.health import router as health_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    logger.info("api_starting env=%s", settings.app_env)
    yield
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

    app.include_router(health_router)
    app.include_router(health_router, prefix="/v1")
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
