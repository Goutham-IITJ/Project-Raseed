import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from backend.app.api.purchases import router as purchase_router
from backend.app.api.routes import router
from backend.app.config import Settings
from backend.app.database import make_engine, make_session_factory
from backend.app.identity.context import TokenVerifier
from backend.app.identity.firebase import FirebaseTokenVerifier
from backend.app.purchases.errors import DomainError

logger = logging.getLogger(__name__)


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def create_app(
    settings: Settings | None = None,
    *,
    verifier: TokenVerifier | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    config = settings or Settings()
    engine = make_engine(config.database_url) if session_factory is None else None
    if session_factory is not None:
        factory = session_factory
    else:
        assert engine is not None
        factory = make_session_factory(engine)
    token_verifier = verifier or FirebaseTokenVerifier(config.firebase_project_id)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            engine.dispose()
        if isinstance(token_verifier, FirebaseTokenVerifier):
            token_verifier.close()

    application = FastAPI(title="Raseed V2", version="0.1.0", lifespan=lifespan)
    application.state.session_factory = factory
    application.state.token_verifier = token_verifier
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "PATCH", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.middleware("http")
    async def no_store(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {
            401: ("unauthorized", "A valid bearer token is required."),
            422: ("validation_error", "Invalid request."),
            503: ("authentication_unavailable", "Authentication is temporarily unavailable."),
        }
        code, message = codes.get(exc.status_code, ("http_error", "Request failed."))
        response = error_response(code, message, exc.status_code)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo arbitrary input or tokens in validation errors.
        return error_response("validation_error", "Invalid request.", 422)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database operation failed (%s)", type(exc).__name__)
        return error_response("database_unavailable", "Database is temporarily unavailable.", 503)

    @application.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(exc.code, exc.message, exc.status_code)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Request failed (%s)", type(exc).__name__)
        return error_response("internal_error", "An unexpected error occurred.", 500)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(router)
    application.include_router(purchase_router)
    return application


app = create_app()
