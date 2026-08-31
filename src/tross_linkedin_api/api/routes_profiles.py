"""Profile resolution endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from tross_linkedin_api.api.deps import get_linkedin_client
from tross_linkedin_api.auth.api_key import require_api_key
from tross_linkedin_api.linkedin.client import LinkedInClient
from tross_linkedin_api.schemas.errors import ProblemDetails
from tross_linkedin_api.schemas.profile_v1 import (
    ProfileResponseV1,
    ResolveProfileRequest,
    build_profile_response,
)
from tross_linkedin_api.url.linkedin_url import canonicalize_linkedin_profile_url


router = APIRouter(prefix="/v1")
_REQUEST_ID_HEADER = {
    "description": "Request correlation identifier.",
    "schema": {"type": "string"},
}
_RETRY_AFTER_HEADER = {
    "description": "Bounded delay in seconds before retrying.",
    "schema": {"type": "integer", "minimum": 0},
}


def _problem_response_spec(*, retry_after: bool = False) -> dict[str, object]:
    headers = {"x-request-id": _REQUEST_ID_HEADER}
    if retry_after:
        headers["retry-after"] = _RETRY_AFTER_HEADER
    return {
        "description": "RFC 9457 Problem Details",
        "headers": headers,
        "content": {
            "application/problem+json": {
                "schema": ProblemDetails.model_json_schema(),
            }
        },
    }


@router.post(
    "/profiles:resolve",
    response_model=ProfileResponseV1,
    responses={
        200: {
            "description": "A strict v1 profile response.",
            "headers": {
                "x-request-id": _REQUEST_ID_HEADER,
                "x-cache": {
                    "description": "Whether Redis served the profile snapshot.",
                    "schema": {"type": "string", "enum": ["hit", "miss"]},
                },
                "cache-control": {
                    "description": "No-store during the uncached vertical slice.",
                    "schema": {"type": "string"},
                },
            },
        },
        **{
            code: _problem_response_spec()
            for code in (400, 401, 403, 404, 422, 500, 502, 504)
        },
        429: _problem_response_spec(retry_after=True),
        503: _problem_response_spec(retry_after=True),
    },
    dependencies=[Depends(require_api_key)],
)
async def resolve_profile(
    body: ResolveProfileRequest,
    request: Request,
    response: Response,
    linkedin_client: LinkedInClient = Depends(get_linkedin_client),
) -> ProfileResponseV1:
    """Resolve a validated LinkedIn URL through the bounded three-call flow."""

    canonical = canonicalize_linkedin_profile_url(body.profile_url)
    profile = await linkedin_client.resolve(canonical.profile_id)
    result = build_profile_response(profile, request_id=request.state.request_id)
    response.headers["x-cache"] = "miss"
    # Until Redis lands, make the zero-lifetime cache envelope explicit to HTTP
    # clients as well as through equal stored/expires timestamps.
    response.headers["cache-control"] = "no-store"
    return result
