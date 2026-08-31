"""Digest-only API-key authentication."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from tross_linkedin_api.errors import ApiKeyInvalidError, ApiKeyMissingError
from tross_linkedin_api.settings import Settings


api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def require_api_key(
    raw_api_key: str | None = Depends(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Authenticate and return only a safe digest prefix for internal use."""

    if raw_api_key is None:
        raise ApiKeyMissingError()
    key_bytes = raw_api_key.encode("utf-8")
    digest = (
        hmac.new(
            settings.api_key_hmac_secret.encode("utf-8"),
            key_bytes,
            hashlib.sha256,
        ).hexdigest()
        if settings.api_key_hmac_secret is not None
        else hashlib.sha256(key_bytes).hexdigest()
    )
    valid = False
    for configured in settings.api_key_hashes:
        valid = hmac.compare_digest(digest, configured) or valid
    if not valid:
        raise ApiKeyInvalidError()
    return digest[:12]
