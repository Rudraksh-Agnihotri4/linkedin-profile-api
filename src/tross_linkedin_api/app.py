"""FastAPI application factory for the minimum profile-resolution slice."""

from __future__ import annotations

import logging
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from tross_linkedin_api.api.routes_health import router as health_router
from tross_linkedin_api.api.routes_profiles import router as profiles_router
from tross_linkedin_api.errors import ServiceError
from tross_linkedin_api.lifespan import build_lifespan
from tross_linkedin_api.schemas.errors import ProblemDetails
from tross_linkedin_api.settings import Settings


logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Create the application with optional test-only dependency injection."""

    app = FastAPI(
        title="Tross LinkedIn Profile API",
        version="0.1.0",
        lifespan=build_lifespan(settings, upstream_transport),
    )
    app.include_router(health_router)
    app.include_router(profiles_router)

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        request.state.request_id = f"req_{uuid.uuid4().hex}"
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "unhandled_exception",
                extra={
                    "request_id": request.state.request_id,
                    "error_type": type(exc).__name__,
                },
            )
            response = _problem_response(request, ServiceError())
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(
        request: Request, exc: ServiceError
    ) -> JSONResponse:
        return _problem_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        malformed_json = any(
            error.get("type") == "json_invalid" for error in exc.errors()
        )
        error = _RequestProblem(
            status_code=400 if malformed_json else 422,
            code="invalid_json" if malformed_json else "invalid_profile_url",
            title="Invalid JSON" if malformed_json else "Invalid LinkedIn profile URL",
            detail=(
                "The request body must contain valid JSON."
                if malformed_json
                else "The URL must be a LinkedIn public profile URL under /in/{slug}."
            ),
        )
        return _problem_response(request, error)

    return app


class _RequestProblem(ServiceError):
    def __init__(
        self, *, status_code: int, code: str, title: str, detail: str
    ) -> None:
        super().__init__()
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail


def _problem_response(request: Request, exc: ServiceError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex}")
    settings: Settings = request.app.state.settings
    problem = ProblemDetails(
        type=f"{settings.public_base_url.rstrip('/')}/problems/{exc.code}",
        title=exc.title,
        status=exc.status_code,
        detail=exc.detail,
        instance=f"{request.url.path}/{request_id}",
        request_id=request_id,
        code=exc.code,
        retry_after_seconds=exc.retry_after_seconds,
    )
    headers: dict[str, str] = {}
    if exc.retry_after_seconds is not None:
        headers["retry-after"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        headers=headers,
        media_type="application/problem+json",
    )
