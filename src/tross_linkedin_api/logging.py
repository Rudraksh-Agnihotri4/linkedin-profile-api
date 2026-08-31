"""Logging helpers that redact secrets before records are emitted."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "authorization",
    "x-api-key",
    "api_key",
    "api_key_hashes",
    "api_key_hmac_secret",
    "cookie",
    "set-cookie",
    "li_at",
    "jsessionid",
    "csrf-token",
    "csrf_token",
    "linkedin_li_at",
    "linkedin_jsessionid",
    "linkedin_csrf_token",
    "redis_url",
}
_INLINE_SECRET = re.compile(
    r"(?i)\b(authorization|x-api-key|api_key(?:_hashes|_hmac_secret)?|cookie|set-cookie|li_at|"
    r"jsessionid|csrf[-_]?token)\b(\s*[=:]\s*)([^\r\n;,]+)"
)
_URL_PASSWORD = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^\s/:@]+:)[^\s@]+(@)")
_REDIS_PASSWORD = re.compile(r"(?i)(\bredis(?:s)?://:)[^\s@]+(@)")


def redact_data(value: Any) -> Any:
    """Return a recursively redacted logging value."""

    if isinstance(value, Mapping):
        return {
            str(key): REDACTED
            if str(key).lower() in _SENSITIVE_KEYS
            else redact_data(child)
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_data(child) for child in value)
    if isinstance(value, list):
        return [redact_data(child) for child in value]
    if isinstance(value, str):
        redacted = _INLINE_SECRET.sub(
            lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value
        )
        redacted = _REDIS_PASSWORD.sub(rf"\1{REDACTED}\2", redacted)
        return _URL_PASSWORD.sub(rf"\1{REDACTED}\2", redacted)
    return value


class SensitiveDataFilter(logging.Filter):
    """Redact message, arguments, and structured extra fields in-place."""

    _STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_data(record.msg)
        record.args = redact_data(record.args)
        for key, value in tuple(record.__dict__.items()):
            if key not in self._STANDARD_FIELDS:
                record.__dict__[key] = redact_data(value)
        return True


def configure_logging(level: str) -> None:
    """Configure a small process logger with the redaction filter installed."""

    root = logging.getLogger()
    root.setLevel(level.upper())
    # HTTPX's default INFO event contains the complete query URL. Provider code
    # emits its own safe query-name/profile-hash event instead.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for handler in root.handlers:
        if not any(isinstance(item, SensitiveDataFilter) for item in handler.filters):
            handler.addFilter(SensitiveDataFilter())
