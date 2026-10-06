from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from private_trading_core.errors import AppError, ForbiddenError, UnauthorizedError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
        return _error_response(request, exc, status_code=401)

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return _error_response(request, exc, status_code=403)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        status_code = 404 if exc.code == "NOT_FOUND" else 400
        if exc.code == "MFA_REQUIRED":
            status_code = 401
        return _error_response(request, exc, status_code=status_code)


def _error_response(request: Request, exc: AppError, *, status_code: int) -> JSONResponse:
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
