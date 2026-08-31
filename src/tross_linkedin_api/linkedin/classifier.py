"""Conservative classification for untrusted LinkedIn responses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any

import httpx


NORMALIZED_MEDIA_TYPE = "application/vnd.linkedin.normalized+json"
_AUTH_MARKERS = (
    "/login",
    "/uas/login",
    "authentication_required",
    "authwall",
    "login__form",
    "logged out",
    "not authenticated",
    "session expired",
    "sign in | linkedin",
)
_CHALLENGE_MARKERS = (
    "/checkpoint",
    "challenge/verify",
    "captcha",
    "security verification",
    "quick security check",
    "unusual activity",
    "verify your identity",
    "account restricted",
)
_RATE_MARKERS = ("too many requests", "rate_limit", "ratelimit", "throttl")
_SIGNAL_KEYS = {
    "code",
    "error",
    "errorcode",
    "message",
    "redirecturl",
    "serviceerrorcode",
    "status",
}


class UpstreamKind(StrEnum):
    SUCCESS_JSON = "success_json"
    AUTH_REQUIRED = "auth_required"
    CHALLENGE = "challenge_or_checkpoint"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"
    MALFORMED_PAYLOAD = "malformed_payload"


@dataclass(frozen=True, slots=True)
class UpstreamClassification:
    kind: UpstreamKind
    payload: dict[str, Any] | None = None
    retry_after_seconds: int | None = None
    safe_to_retry: bool = False


def classify_response(response: httpx.Response) -> UpstreamClassification:
    """Classify one response without exposing its body or headers to callers."""

    retry_after = _retry_after_seconds(response.headers.get("retry-after"))
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    location = response.headers.get("location", "").lower()

    if response.status_code in {401, 403, 999}:
        return UpstreamClassification(UpstreamKind.AUTH_REQUIRED)
    if response.status_code == 429:
        return UpstreamClassification(UpstreamKind.RATE_LIMITED, None, retry_after)
    if 300 <= response.status_code < 400 or location:
        markers = f"{location} {response.text[:8192].lower()}"
        if _contains(markers, _CHALLENGE_MARKERS):
            return UpstreamClassification(UpstreamKind.CHALLENGE)
        if _contains(markers, _AUTH_MARKERS):
            return UpstreamClassification(UpstreamKind.AUTH_REQUIRED)
        return UpstreamClassification(UpstreamKind.PERMANENT_FAILURE)

    body_prefix = response.text[:65536]
    looks_like_html = body_prefix.lstrip(" \t\r\n\ufeff").lower().startswith(
        ("<!doctype html", "<html", "<head", "<body", "<form")
    )
    if "html" in content_type or looks_like_html:
        body = body_prefix.lower()
        if _contains(body, _CHALLENGE_MARKERS):
            return UpstreamClassification(UpstreamKind.CHALLENGE)
        if _contains(body, _AUTH_MARKERS):
            return UpstreamClassification(UpstreamKind.AUTH_REQUIRED)
        if _contains(body, _RATE_MARKERS):
            return UpstreamClassification(UpstreamKind.RATE_LIMITED, None, retry_after)
        if "retry-after" in response.headers:
            return UpstreamClassification(UpstreamKind.RATE_LIMITED, None, retry_after)
        return UpstreamClassification(UpstreamKind.MALFORMED_PAYLOAD)

    if "retry-after" in response.headers:
        return UpstreamClassification(UpstreamKind.RATE_LIMITED, None, retry_after)
    if response.status_code in {408, 425} or 500 <= response.status_code < 600:
        return UpstreamClassification(
            UpstreamKind.TRANSIENT_FAILURE,
            safe_to_retry=True,
        )
    if not 200 <= response.status_code < 300:
        return UpstreamClassification(UpstreamKind.PERMANENT_FAILURE)
    expected_json = (
        content_type == "application/json"
        or content_type.endswith("+json")
        or NORMALIZED_MEDIA_TYPE in content_type
    )
    if not expected_json:
        body = body_prefix.lower()
        if _contains(body, _CHALLENGE_MARKERS):
            return UpstreamClassification(UpstreamKind.CHALLENGE)
        if _contains(body, _AUTH_MARKERS):
            return UpstreamClassification(UpstreamKind.AUTH_REQUIRED)
        if _contains(body, _RATE_MARKERS):
            return UpstreamClassification(UpstreamKind.RATE_LIMITED, None, retry_after)
        return UpstreamClassification(UpstreamKind.MALFORMED_PAYLOAD)
    try:
        payload = response.json()
    except ValueError:
        return UpstreamClassification(UpstreamKind.MALFORMED_PAYLOAD)
    if not isinstance(payload, dict):
        return UpstreamClassification(UpstreamKind.MALFORMED_PAYLOAD)
    signal_text = " ".join(_json_signal_strings(payload)).lower()
    if _contains(signal_text, _CHALLENGE_MARKERS):
        return UpstreamClassification(UpstreamKind.CHALLENGE)
    if _contains(signal_text, _AUTH_MARKERS):
        return UpstreamClassification(UpstreamKind.AUTH_REQUIRED)
    if _contains(signal_text, _RATE_MARKERS):
        return UpstreamClassification(UpstreamKind.RATE_LIMITED, None, retry_after)
    if payload.get("errors"):
        return UpstreamClassification(UpstreamKind.PERMANENT_FAILURE)
    if not isinstance(payload.get("data"), dict) or not isinstance(
        payload.get("included"), list
    ):
        return UpstreamClassification(UpstreamKind.MALFORMED_PAYLOAD)
    return UpstreamClassification(UpstreamKind.SUCCESS_JSON, payload)


def _contains(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _json_signal_strings(value: Any) -> list[str]:
    result: list[str] = []
    stack = [value]
    inspected = 0
    while stack and inspected < 1000:
        current = stack.pop()
        inspected += 1
        if isinstance(current, Mapping):
            for key, child in current.items():
                normalized_key = str(key).lower()
                # Normalized `included` entities contain profile data, not
                # response-control signals. Scanning them can misclassify a
                # legitimate profile whose content mentions login or throttling.
                if normalized_key == "included":
                    continue
                if normalized_key in _SIGNAL_KEYS and isinstance(child, (str, int)):
                    result.append(str(child)[:1000])
                elif isinstance(child, (Mapping, list)):
                    stack.append(child)
        elif isinstance(current, list):
            stack.extend(reversed(current[:100]))
    return result


def _retry_after_seconds(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0, int((parsed - datetime.now(UTC)).total_seconds()))
