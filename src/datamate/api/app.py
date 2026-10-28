"""FastAPI application and routes."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from datamate.business_store import BusinessNotFoundError, BusinessStore
from datamate.config import Settings
from datamate.llm.placeholder import PlaceholderLLMClient
from datamate.models import (
    AnswerRequest,
    AnswerResponse,
    ErrorBody,
    ErrorResponse,
    StatusResponse,
)
from datamate.services import AnswerService, LLMClientError, LLMTimeoutError

logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump())


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an API application with configured dependencies."""

    configured_settings = settings or Settings.from_environment()
    business_store = BusinessStore(configured_settings.data_root)
    if configured_settings.llm_provider != "placeholder":
        raise ValueError("Only the placeholder LLM provider is available")
    service = AnswerService(
        llm_client=PlaceholderLLMClient(),
        timeout_seconds=configured_settings.llm_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        logging.basicConfig(level=configured_settings.log_level)
        yield

    application = FastAPI(title="DataMate API", version="0.1.0", lifespan=lifespan)
    application.state.answer_service = service
    application.state.business_store = business_store
    application.state.settings = configured_settings

    @application.middleware("http")
    async def log_request(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request_complete method=%s path=%s status=%s question_id=%s "
            "business_id=%s elapsed_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            getattr(request.state, "question_id", None),
            getattr(request.state, "business_id", None),
            elapsed_ms,
        )
        return response

    @application.exception_handler(BusinessNotFoundError)
    async def business_not_found(
        _: Request, __: BusinessNotFoundError
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "BUSINESS_NOT_FOUND",
            "Business data folder is unavailable",
        )

    @application.exception_handler(LLMTimeoutError)
    async def llm_timeout(_: Request, __: LLMTimeoutError) -> JSONResponse:
        return _error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "LLM_TIMEOUT",
            "The answer provider took too long",
        )

    @application.exception_handler(LLMClientError)
    async def llm_failure(_: Request, __: LLMClientError) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "LLM_CLIENT_ERROR",
            "The answer provider failed to produce a result",
        )

    @application.get("/health", response_model=StatusResponse)
    async def health() -> StatusResponse:
        return StatusResponse(status="ok")

    @application.get("/ready", response_model=StatusResponse)
    async def ready() -> StatusResponse:
        store = cast(BusinessStore, application.state.business_store)
        if not store.is_ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Data root is unavailable",
            )
        return StatusResponse(status="ready")

    def resolve_business(
        request: AnswerRequest,
        http_request: Request,
    ) -> Path:
        """Resolve the request's business folder before calling the route."""

        http_request.state.question_id = request.id
        http_request.state.business_id = request.business_id
        store = cast(BusinessStore, application.state.business_store)
        return store.resolve(request.business_id)

    @application.post("/v1/answer", response_model=AnswerResponse)
    async def answer(
        request: AnswerRequest,
        business_path: Annotated[Path, Depends(resolve_business)],
    ) -> AnswerResponse:
        current_settings = cast(Settings, application.state.settings)
        if len(request.question) > current_settings.max_question_length:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Question is too long",
            )
        answer_service = cast(AnswerService, application.state.answer_service)
        return await answer_service.answer(request, business_path)

    return application


app = create_app()
