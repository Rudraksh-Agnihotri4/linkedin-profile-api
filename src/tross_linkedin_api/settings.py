"""Typed settings for the minimum production profile-resolution slice."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from math import isfinite
from urllib.parse import urlsplit


_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration loaded from environment variables.

    Secret fields are deliberately omitted from the generated representation.
    The current milestone does not initialize Redis or any deferred safety
    components.
    """

    app_env: str = "local"
    app_name: str = "tross-linkedin-profile-api"
    public_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    api_key_hashes: frozenset[str] = field(default_factory=frozenset, repr=False)
    api_key_hmac_secret: str | None = field(default=None, repr=False)
    linkedin_base_url: str = "https://www.linkedin.com"
    linkedin_user_agent: str = "tross-linkedin-profile-api/0.1"
    linkedin_li_at: str = field(default="", repr=False)
    linkedin_jsessionid: str = field(default="", repr=False)
    linkedin_csrf_token: str = field(default="", repr=False)
    httpx_max_connections: int = 10
    httpx_max_keepalive_connections: int = 5
    httpx_keepalive_expiry_seconds: float = 30.0
    upstream_connect_timeout_seconds: float = 10.0
    upstream_read_timeout_seconds: float = 15.0
    upstream_write_timeout_seconds: float = 10.0
    upstream_pool_timeout_seconds: float = 10.0
    upstream_cooldown_default_seconds: int = 60
    upstream_retry_after_max_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.app_env not in {"local", "staging", "production", "test"}:
            raise ValueError("APP_ENV must be local, staging, production, or test")
        if not self.app_name.strip():
            raise ValueError("APP_NAME must not be empty")
        if self.log_level.upper() not in {
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }:
            raise ValueError("LOG_LEVEL is invalid")
        if not self.api_key_hashes:
            raise ValueError("API_KEY_HASHES must contain at least one digest")
        if any(not _SHA256_HEX.fullmatch(value) for value in self.api_key_hashes):
            raise ValueError("API_KEY_HASHES must contain SHA-256/HMAC hex digests")
        if self.api_key_hmac_secret is not None and (
            not self.api_key_hmac_secret
            or _has_control_characters(self.api_key_hmac_secret)
        ):
            raise ValueError("API_KEY_HMAC_SECRET is invalid")
        _validate_public_base_url(self.public_base_url)
        if self.app_env == "production" and urlsplit(self.public_base_url).scheme != "https":
            raise ValueError("PUBLIC_BASE_URL must use HTTPS in production")
        _validate_linkedin_base_url(self.linkedin_base_url)
        if not self.linkedin_user_agent.strip():
            raise ValueError("LINKEDIN_USER_AGENT must not be empty")
        if not all(
            (
                self.linkedin_li_at,
                self.linkedin_jsessionid,
                self.linkedin_csrf_token,
            )
        ):
            raise ValueError("LinkedIn session configuration is incomplete")
        if any(
            _has_control_characters(value)
            for value in (
                self.linkedin_user_agent,
                self.linkedin_li_at,
                self.linkedin_jsessionid,
                self.linkedin_csrf_token,
            )
        ):
            raise ValueError("LinkedIn header and cookie configuration is invalid")
        if not _is_cookie_value(self.linkedin_li_at):
            raise ValueError("LINKEDIN_LI_AT is not a valid cookie value")
        jsessionid_token = _unquoted_jsessionid(self.linkedin_jsessionid)
        if not jsessionid_token.startswith("ajax:"):
            raise ValueError("LINKEDIN_JSESSIONID must contain the expected ajax token")
        if self.linkedin_csrf_token != jsessionid_token:
            raise ValueError(
                "LINKEDIN_CSRF_TOKEN must equal LINKEDIN_JSESSIONID without quotes"
            )
        positive_integers = (
            self.httpx_max_connections,
            self.httpx_max_keepalive_connections,
            self.upstream_cooldown_default_seconds,
            self.upstream_retry_after_max_seconds,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in positive_integers
        ):
            raise ValueError("HTTP client counts and retry bounds must be positive")
        positive_numbers = (
            self.httpx_keepalive_expiry_seconds,
            self.upstream_connect_timeout_seconds,
            self.upstream_read_timeout_seconds,
            self.upstream_write_timeout_seconds,
            self.upstream_pool_timeout_seconds,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
            for value in positive_numbers
        ):
            raise ValueError("HTTP client limits and timeouts must be positive")
        if self.httpx_max_keepalive_connections > self.httpx_max_connections:
            raise ValueError("keep-alive connections cannot exceed max connections")
        if self.upstream_cooldown_default_seconds > self.upstream_retry_after_max_seconds:
            raise ValueError("default upstream cooldown cannot exceed Retry-After maximum")

    @property
    def linkedin_jsessionid_cookie_value(self) -> str:
        """Return the proven literal-quoted JSESSIONID cookie representation."""

        return f'"{_unquoted_jsessionid(self.linkedin_jsessionid)}"'

    @classmethod
    def from_env(cls) -> Settings:
        """Load the subset of settings required by this milestone."""

        raw_hashes = os.environ.get("API_KEY_HASHES", "")
        hashes = frozenset(
            item.strip().lower() for item in raw_hashes.split(",") if item.strip()
        )
        return cls(
            app_env=os.environ.get("APP_ENV", "local").lower(),
            app_name=os.environ.get("APP_NAME", "tross-linkedin-profile-api"),
            public_base_url=os.environ.get(
                "PUBLIC_BASE_URL", "http://localhost:8000"
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            api_key_hashes=hashes,
            api_key_hmac_secret=os.environ.get("API_KEY_HMAC_SECRET") or None,
            linkedin_base_url=os.environ.get(
                "LINKEDIN_BASE_URL", "https://www.linkedin.com"
            ),
            linkedin_user_agent=os.environ.get("LINKEDIN_USER_AGENT", ""),
            linkedin_li_at=os.environ.get("LINKEDIN_LI_AT", ""),
            linkedin_jsessionid=os.environ.get("LINKEDIN_JSESSIONID", ""),
            linkedin_csrf_token=os.environ.get("LINKEDIN_CSRF_TOKEN", ""),
            httpx_max_connections=_env_int("HTTPX_MAX_CONNECTIONS", 10),
            httpx_max_keepalive_connections=_env_int(
                "HTTPX_MAX_KEEPALIVE_CONNECTIONS", 5
            ),
            httpx_keepalive_expiry_seconds=_env_float(
                "HTTPX_KEEPALIVE_EXPIRY_SECONDS", 30.0
            ),
            upstream_connect_timeout_seconds=_env_float(
                "UPSTREAM_CONNECT_TIMEOUT_SECONDS", 10.0
            ),
            upstream_read_timeout_seconds=_env_float(
                "UPSTREAM_READ_TIMEOUT_SECONDS", 15.0
            ),
            upstream_write_timeout_seconds=_env_float(
                "UPSTREAM_WRITE_TIMEOUT_SECONDS", 10.0
            ),
            upstream_pool_timeout_seconds=_env_float(
                "UPSTREAM_POOL_TIMEOUT_SECONDS", 10.0
            ),
            upstream_cooldown_default_seconds=_env_int(
                "UPSTREAM_COOLDOWN_DEFAULT_SECONDS", 60
            ),
            upstream_retry_after_max_seconds=_env_int(
                "UPSTREAM_RETRY_AFTER_MAX_SECONDS", 3600
            ),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return default if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return default if raw is None else float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _validate_linkedin_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if not (
        parsed.scheme == "https"
        and parsed.hostname == "www.linkedin.com"
        and parsed.netloc == "www.linkedin.com"
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    ):
        raise ValueError("LINKEDIN_BASE_URL must be the controlled LinkedIn origin")


def _validate_public_base_url(value: str) -> None:
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL") from exc
    if not (
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    ):
        raise ValueError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL")


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)


def _is_cookie_value(value: str) -> bool:
    return bool(value) and all(
        0x21 <= ord(character) <= 0x7E and character not in {'"', ",", ";", "\\"}
        for character in value
    )


def _unquoted_jsessionid(value: str) -> str:
    starts_quoted = value.startswith('"')
    ends_quoted = value.endswith('"')
    if starts_quoted != ends_quoted:
        raise ValueError("LINKEDIN_JSESSIONID has unmatched literal quotes")
    token = value[1:-1] if starts_quoted else value
    if not _is_cookie_value(token):
        raise ValueError("LINKEDIN_JSESSIONID is not a valid cookie value")
    return token
