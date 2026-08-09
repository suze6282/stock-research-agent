from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import partial
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars

from stock_research_agent import __version__
from stock_research_agent.api.errors import ApiError
from stock_research_agent.api.router import create_api_router
from stock_research_agent.config import Settings
from stock_research_agent.db.session import (
    check_database,
    create_engine_from_settings,
    create_session_factory,
)
from stock_research_agent.logging import configure_logging

RequestHandler = Callable[[Request], Awaitable[Response]]
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None, bool | None]]


def _database_not_configured() -> None:
    raise SQLAlchemyError("Database is not configured")


def _create_lifespan(settings: Settings) -> Lifespan:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine: Engine | None = None
        session_factory = None
        if settings.database_url is None:
            app.state.database_check = _database_not_configured
        else:
            engine = create_engine_from_settings(settings)
            app.state.database_check = partial(check_database, engine)
            session_factory = create_session_factory(engine)
        app.state.database_engine = engine
        app.state.database_session_factory = session_factory

        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    return lifespan


def _error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request.state.request_id,
            }
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings)

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        lifespan=_create_lifespan(resolved_settings),
    )
    app.state.settings = resolved_settings
    logger = structlog.get_logger()

    @app.middleware("http")
    async def add_request_id(request: Request, call_next: RequestHandler) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        clear_contextvars()
        bind_contextvars(request_id=request_id)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.error(
                    "request_failed",
                    request_id=request_id,
                    error_type=type(exc).__name__,
                )
                response = _error_response(
                    request,
                    code="INTERNAL_SERVER_ERROR",
                    message="Internal server error",
                    status_code=500,
                )
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )
            return response
        finally:
            clear_contextvars()

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        logger.warning(
            "api_request_failed",
            request_id=request.state.request_id,
            error_type=type(exc.__cause__ or exc).__name__,
            code=exc.code,
        )
        return _error_response(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "api_request_failed",
            request_id=request.state.request_id,
            error_type=type(exc).__name__,
            code="REQUEST_VALIDATION_ERROR",
        )
        return _error_response(
            request,
            code="REQUEST_VALIDATION_ERROR",
            message="Request validation failed",
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def handle_unknown_error(request: Request, _exc: Exception) -> JSONResponse:
        return _error_response(
            request,
            code="INTERNAL_SERVER_ERROR",
            message="Internal server error",
            status_code=500,
        )

    app.include_router(create_api_router(resolved_settings))
    return app


app = create_app()
