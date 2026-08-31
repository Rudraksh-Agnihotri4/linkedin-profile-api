"""Stable internal errors mapped to public Problem Details responses."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for expected, client-safe service failures."""

    status_code = 500
    code = "internal_error"
    title = "Internal server error"
    detail = "The service could not complete the request."

    def __init__(self, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(self.code)
        self.retry_after_seconds = retry_after_seconds


class InvalidProfileUrlError(ServiceError):
    status_code = 422
    code = "invalid_profile_url"
    title = "Invalid LinkedIn profile URL"
    detail = "The URL must be a LinkedIn public profile URL under /in/{slug}."


class ApiKeyMissingError(ServiceError):
    status_code = 401
    code = "api_key_missing"
    title = "API key required"
    detail = "A valid x-api-key header is required."


class ApiKeyInvalidError(ServiceError):
    status_code = 401
    code = "api_key_invalid"
    title = "Invalid API key"
    detail = "The supplied API key is not valid."


class LinkedInAuthRequiredError(ServiceError):
    status_code = 503
    code = "linkedin_auth_required"
    title = "LinkedIn authentication required"
    detail = "The upstream LinkedIn session is unavailable."


class LinkedInChallengeError(ServiceError):
    status_code = 503
    code = "linkedin_challenge_required"
    title = "LinkedIn challenge required"
    detail = "LinkedIn requires operator attention before requests can continue."


class LinkedInRateLimitedError(ServiceError):
    status_code = 503
    code = "linkedin_rate_limited"
    title = "LinkedIn temporarily unavailable"
    detail = "LinkedIn is temporarily rate limiting profile retrieval."


class UpstreamBadResponseError(ServiceError):
    status_code = 502
    code = "upstream_bad_response"
    title = "Upstream response unavailable"
    detail = "LinkedIn returned a response that could not be used safely."


class UpstreamTimeoutError(ServiceError):
    status_code = 504
    code = "upstream_timeout"
    title = "Upstream request timed out"
    detail = "LinkedIn did not respond within the bounded timeout."
