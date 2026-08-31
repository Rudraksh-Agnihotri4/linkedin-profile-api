"""Three-call LinkedIn provider orchestrator."""

from __future__ import annotations

from typing import Any

import httpx

from tross_linkedin_api.domain.profile import DomainProfile
from tross_linkedin_api.errors import (
    LinkedInAuthRequiredError,
    LinkedInChallengeError,
    LinkedInRateLimitedError,
    UpstreamBadResponseError,
    UpstreamTimeoutError,
)
from tross_linkedin_api.linkedin.classifier import (
    UpstreamClassification,
    UpstreamKind,
    classify_response,
)
from tross_linkedin_api.linkedin.parser import extract_profile_urn, parse_profile
from tross_linkedin_api.linkedin.transport import (
    LinkedInTransport,
    VoyagerRequest,
    build_cards_request,
    build_components_request,
    build_identity_request,
)


class LinkedInClient:
    """Resolve one canonical profile id through the proven request sequence."""

    def __init__(
        self,
        transport: LinkedInTransport,
        *,
        retry_after_default_seconds: int = 60,
        retry_after_max_seconds: int = 3600,
    ) -> None:
        self._transport = transport
        self._retry_after_default_seconds = retry_after_default_seconds
        self._retry_after_max_seconds = retry_after_max_seconds

    async def resolve(self, profile_id: str) -> DomainProfile:
        identity = await self._fetch(build_identity_request(profile_id), profile_id)
        profile_urn = extract_profile_urn(
            identity,
            expected_profile_id=profile_id,
        )
        components = await self._fetch(
            build_components_request(profile_urn),
            profile_id,
        )
        cards = await self._fetch(build_cards_request(profile_urn), profile_id)
        return parse_profile(
            profile_id=profile_id,
            profile_urn=profile_urn,
            payloads=(identity, components, cards),
        )

    async def _fetch(
        self, request: VoyagerRequest, profile_id: str
    ) -> dict[str, Any]:
        try:
            response = await self._transport.send(request, profile_id=profile_id)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError() from exc
        except httpx.RequestError as exc:
            raise UpstreamBadResponseError() from exc
        classification = classify_response(response)
        return _payload_or_raise(
            classification,
            retry_after_default_seconds=self._retry_after_default_seconds,
            retry_after_max_seconds=self._retry_after_max_seconds,
        )


def _payload_or_raise(
    classification: UpstreamClassification,
    *,
    retry_after_default_seconds: int,
    retry_after_max_seconds: int,
) -> dict[str, Any]:
    if classification.kind is UpstreamKind.SUCCESS_JSON:
        if classification.payload is None:
            raise UpstreamBadResponseError()
        return classification.payload
    if classification.kind is UpstreamKind.AUTH_REQUIRED:
        raise LinkedInAuthRequiredError()
    if classification.kind is UpstreamKind.CHALLENGE:
        raise LinkedInChallengeError()
    if classification.kind is UpstreamKind.RATE_LIMITED:
        retry_after = min(
            classification.retry_after_seconds
            if classification.retry_after_seconds is not None
            else retry_after_default_seconds,
            retry_after_max_seconds,
        )
        raise LinkedInRateLimitedError(retry_after_seconds=retry_after)
    raise UpstreamBadResponseError()
