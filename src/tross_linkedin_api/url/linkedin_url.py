"""Strict LinkedIn public-profile URL canonicalization."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from tross_linkedin_api.errors import InvalidProfileUrlError


MAX_PROFILE_URL_LENGTH = 2048
_PATH = re.compile(
    r"/in/(?P<slug>[A-Za-z0-9-]{3,100})(?:/(?P<language>[a-z]{2}))?/?"
)
_COUNTRY_HOST = re.compile(r"[a-z]{2}\.linkedin\.com")


@dataclass(frozen=True, slots=True)
class CanonicalProfileUrl:
    """Safe canonical identifiers derived from an untrusted input URL."""

    profile_id: str
    canonical_public_url: str
    input_host_type: str
    language: str | None = None


def canonicalize_linkedin_profile_url(value: str) -> CanonicalProfileUrl:
    """Validate a public profile URL without ever fetching the supplied URL."""

    if not isinstance(value, str):
        raise InvalidProfileUrlError()
    candidate = value.strip(" ")
    if not candidate or len(candidate) > MAX_PROFILE_URL_LENGTH:
        raise InvalidProfileUrlError()
    if any(_is_disallowed_character(character) for character in candidate):
        raise InvalidProfileUrlError()

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise InvalidProfileUrlError() from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise InvalidProfileUrlError()
    if (
        parsed.username is not None
        or parsed.password is not None
        or port is not None
        or ":" in parsed.netloc
    ):
        raise InvalidProfileUrlError()
    if not parsed.hostname:
        raise InvalidProfileUrlError()
    if not parsed.hostname.isascii():
        raise InvalidProfileUrlError()

    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InvalidProfileUrlError() from exc
    if host == "linkedin.com":
        host_type = "root"
    elif host == "www.linkedin.com":
        host_type = "www"
    elif _COUNTRY_HOST.fullmatch(host):
        host_type = "country"
    else:
        raise InvalidProfileUrlError()

    match = _PATH.fullmatch(parsed.path)
    if match is None:
        raise InvalidProfileUrlError()
    profile_id = match.group("slug").lower()
    if profile_id == "linkedin":
        raise InvalidProfileUrlError()
    language = match.group("language")
    return CanonicalProfileUrl(
        profile_id=profile_id,
        canonical_public_url=f"https://www.linkedin.com/in/{profile_id}",
        input_host_type=host_type,
        language=language,
    )


def _is_disallowed_character(character: str) -> bool:
    codepoint = ord(character)
    return codepoint < 0x20 or codepoint == 0x7F or unicodedata.category(character)[0] == "C"
