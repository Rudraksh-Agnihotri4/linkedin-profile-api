"""RFC 9457 Problem Details response schema."""

from __future__ import annotations

from pydantic import BaseModel, NonNegativeInt

from tross_linkedin_api.schemas.common import STRICT_MODEL_CONFIG


class ProblemDetails(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    type: str
    title: str
    status: int
    detail: str
    instance: str
    request_id: str
    code: str
    retry_after_seconds: NonNegativeInt | None = None
