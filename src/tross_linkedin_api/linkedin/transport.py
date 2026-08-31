"""Controlled construction and execution of the three proven Voyager calls."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx


GRAPHQL_PATH = "/voyager/api/graphql"
IDENTITY_QUERY_ID = (
    "voyagerIdentityDashProfiles.34ead06db82a2cc9a778fac97f69ad6a"
)
COMPONENTS_QUERY_ID = (
    "voyagerIdentityDashProfileComponents.86824295e1093fb0f5acdd8d57213aaa"
)
CARDS_QUERY_ID = (
    "voyagerIdentityDashProfileCards.aec4c2601fac8c5f615c7630b8db1ab3"
)
COMPONENTS_SECTION_TYPE = "content-collections"
CARDS_SECTION_TYPE = "CONTENT_COLLECTIONS_DETAILS"
_PROFILE_ID = re.compile(r"[a-z0-9-]{3,100}")
_PROFILE_URN = re.compile(r"urn:li:fsd_profile:[A-Za-z0-9_-]{1,256}")
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VoyagerRequest:
    query_name: str
    query_id: str
    relative_url: str


def build_identity_request(profile_id: str) -> VoyagerRequest:
    if not _PROFILE_ID.fullmatch(profile_id):
        raise ValueError("profile id is not canonical")
    variables = f"(vanityName:{profile_id})"
    return _build_request("voyagerIdentityDashProfiles", IDENTITY_QUERY_ID, variables)


def build_components_request(profile_urn: str) -> VoyagerRequest:
    _validate_profile_urn(profile_urn)
    encoded_urn = quote(profile_urn, safe="")
    variables = (
        f"(profileUrn:{encoded_urn},sectionType:{COMPONENTS_SECTION_TYPE})"
    )
    return _build_request(
        "voyagerIdentityDashProfileComponents",
        COMPONENTS_QUERY_ID,
        variables,
    )


def build_cards_request(profile_urn: str) -> VoyagerRequest:
    _validate_profile_urn(profile_urn)
    encoded_urn = quote(profile_urn, safe="")
    variables = f"(profileUrn:{encoded_urn},sectionType:{CARDS_SECTION_TYPE})"
    return _build_request(
        "voyagerIdentityDashProfileCards",
        CARDS_QUERY_ID,
        variables,
    )


class LinkedInTransport:
    """Execute request specifications using the lifespan-owned client."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    async def send(self, request: VoyagerRequest, *, profile_id: str) -> httpx.Response:
        logger.info(
            "linkedin_request",
            extra={
                "query_name": request.query_name,
                "profile_id_hash": hashlib.sha256(profile_id.encode()).hexdigest(),
            },
        )
        return await self._http_client.get(request.relative_url)


def _build_request(query_name: str, query_id: str, variables: str) -> VoyagerRequest:
    relative_url = (
        f"{GRAPHQL_PATH}?includeWebMetadata=true&variables={variables}&queryId={query_id}"
    )
    return VoyagerRequest(query_name, query_id, relative_url)


def _validate_profile_urn(profile_urn: str) -> None:
    if not _PROFILE_URN.fullmatch(profile_urn):
        raise ValueError("profile URN is not a controlled fsd_profile URN")
