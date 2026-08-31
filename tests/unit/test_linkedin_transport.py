"""Exact proven Voyager request-construction tests."""

from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

from tross_linkedin_api.linkedin.transport import (
    CARDS_QUERY_ID,
    COMPONENTS_QUERY_ID,
    IDENTITY_QUERY_ID,
    build_cards_request,
    build_components_request,
    build_identity_request,
)


class LinkedInTransportTests(unittest.TestCase):
    profile_urn = "urn:li:fsd_profile:ACoAAExample123"

    def test_identity_uses_exact_current_contract(self) -> None:
        request = build_identity_request("example-person")
        self.assertEqual(
            request.relative_url,
            "/voyager/api/graphql?includeWebMetadata=true&"
            "variables=(vanityName:example-person)&"
            f"queryId={IDENTITY_QUERY_ID}",
        )
        query = parse_qs(urlsplit(request.relative_url).query)
        self.assertEqual(query["includeWebMetadata"], ["true"])
        self.assertEqual(query["variables"], ["(vanityName:example-person)"])
        self.assertEqual(query["queryId"], [IDENTITY_QUERY_ID])

    def test_components_uses_exact_current_contract(self) -> None:
        request = build_components_request(self.profile_urn)
        self.assertEqual(
            request.relative_url,
            "/voyager/api/graphql?includeWebMetadata=true&"
            "variables=(profileUrn:urn%3Ali%3Afsd_profile%3AACoAAExample123,"
            "sectionType:content-collections)&"
            f"queryId={COMPONENTS_QUERY_ID}",
        )
        query = parse_qs(urlsplit(request.relative_url).query)
        self.assertEqual(
            query["variables"],
            [
                "(profileUrn:urn:li:fsd_profile:ACoAAExample123,"
                "sectionType:content-collections)"
            ],
        )
        self.assertEqual(query["queryId"], [COMPONENTS_QUERY_ID])

    def test_cards_uses_exact_current_contract(self) -> None:
        request = build_cards_request(self.profile_urn)
        self.assertEqual(
            request.relative_url,
            "/voyager/api/graphql?includeWebMetadata=true&"
            "variables=(profileUrn:urn%3Ali%3Afsd_profile%3AACoAAExample123,"
            "sectionType:CONTENT_COLLECTIONS_DETAILS)&"
            f"queryId={CARDS_QUERY_ID}",
        )
        query = parse_qs(urlsplit(request.relative_url).query)
        self.assertEqual(
            query["variables"],
            [
                "(profileUrn:urn:li:fsd_profile:ACoAAExample123,"
                "sectionType:CONTENT_COLLECTIONS_DETAILS)"
            ],
        )
        self.assertEqual(query["queryId"], [CARDS_QUERY_ID])

    def test_only_controlled_identifiers_are_accepted(self) -> None:
        with self.assertRaises(ValueError):
            build_identity_request("https://evil.example/profile")
        with self.assertRaises(ValueError):
            build_components_request("urn:li:other:unsafe")


if __name__ == "__main__":
    unittest.main()
