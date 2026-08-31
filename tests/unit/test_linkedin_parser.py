"""Sanitized Spike 0B fixture parser and strict-schema tests."""

from __future__ import annotations

import copy
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from tross_linkedin_api.errors import UpstreamBadResponseError
from tross_linkedin_api.linkedin.parser import (
    extract_profile_urn,
    merge_entities_by_urn,
    parse_profile,
)
from tross_linkedin_api.schemas.profile_v1 import (
    CacheMetadataV1,
    ExperienceItemV1,
    ImageV1,
    ProfileResponseV1,
    SectionStatusV1,
    build_profile_response,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "linkedin"
PROFILE_URN = "urn:li:fsd_profile:ACoAAExample123"


def fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = fixture("spike0b_identity.json")
        self.components = fixture("spike0b_components.json")
        self.cards = fixture("spike0b_cards.json")

    def test_extracts_profile_urn_and_merges_entities(self) -> None:
        self.assertEqual(
            extract_profile_urn(
                self.identity,
                expected_profile_id="example-person",
            ),
            PROFILE_URN,
        )
        merged = merge_entities_by_urn(
            (self.identity, self.components, self.cards)
        )
        profile = merged[PROFILE_URN]
        self.assertEqual(profile["firstName"], "Example")
        self.assertEqual(profile["lastName"], "Person")
        self.assertEqual(profile["position"], "urn:li:fsd_position:synthetic")

    def test_maps_only_safely_evidenced_fields(self) -> None:
        fetched_at = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
        profile = parse_profile(
            profile_id="example-person",
            profile_urn=PROFILE_URN,
            payloads=(self.identity, self.components, self.cards),
            fetched_at=fetched_at,
        )
        self.assertEqual(profile.identity.name, "Example Person")
        self.assertEqual(profile.identity.headline, "Software Engineer")
        self.assertEqual(profile.identity.location, "Example City")
        self.assertEqual(profile.images.profile.width, 400)  # type: ignore[union-attr]
        self.assertEqual(profile.images.background.width, 800)  # type: ignore[union-attr]
        self.assertIsNone(profile.about.value)
        for section in (
            profile.experience,
            profile.education,
            profile.skills,
            profile.certifications,
            profile.languages,
        ):
            self.assertEqual(section.status, "unavailable")
            self.assertEqual(section.items, ())

    def test_unknown_fields_are_ignored(self) -> None:
        identity = copy.deepcopy(self.identity)
        included = identity["included"]
        assert isinstance(included, list)
        assert isinstance(included[0], dict)
        included[0]["futureUnknownField"] = {"nested": [1, 2, 3]}
        profile = parse_profile(
            profile_id="example-person",
            profile_urn=PROFILE_URN,
            payloads=(identity, self.components, self.cards),
        )
        self.assertEqual(profile.identity.name, "Example Person")

    def test_missing_core_name_fails_closed(self) -> None:
        identity = copy.deepcopy(self.identity)
        included = identity["included"]
        assert isinstance(included, list)
        assert isinstance(included[0], dict)
        included[0]["firstName"] = None
        included[0]["lastName"] = None
        with self.assertRaises(UpstreamBadResponseError):
            parse_profile(
                profile_id="example-person",
                profile_urn=PROFILE_URN,
                payloads=(identity, self.components, self.cards),
            )

    def test_mismatched_profile_identifier_fails_before_fanout(self) -> None:
        with self.assertRaises(UpstreamBadResponseError):
            extract_profile_urn(
                self.identity,
                expected_profile_id="different-person",
            )

    def test_identity_must_be_root_referenced_not_merely_included(self) -> None:
        identity = copy.deepcopy(self.identity)
        included = identity["included"]
        assert isinstance(included, list)
        assert isinstance(included[0], dict)
        decoy = copy.deepcopy(included[0])
        decoy["entityUrn"] = "urn:li:fsd_profile:ACoAADecoy456"
        decoy["publicIdentifier"] = "example-person"
        included[0]["publicIdentifier"] = "different-person"
        included.append(decoy)
        with self.assertRaises(UpstreamBadResponseError):
            extract_profile_urn(identity, expected_profile_id="example-person")

    def test_every_fanout_payload_must_correlate_to_the_profile_urn(self) -> None:
        components = copy.deepcopy(self.components)
        included = components["included"]
        assert isinstance(included, list)
        components["included"] = [
            entity
            for entity in included
            if not (
                isinstance(entity, dict) and entity.get("entityUrn") == PROFILE_URN
            )
        ]
        with self.assertRaises(UpstreamBadResponseError):
            parse_profile(
                profile_id="example-person",
                profile_urn=PROFILE_URN,
                payloads=(self.identity, components, self.cards),
            )

        cards = copy.deepcopy(self.cards)
        cards_included = cards["included"]
        assert isinstance(cards_included, list)
        assert isinstance(cards_included[0], dict)
        cards_included[0]["publicIdentifier"] = "different-person"
        with self.assertRaises(UpstreamBadResponseError):
            parse_profile(
                profile_id="example-person",
                profile_urn=PROFILE_URN,
                payloads=(self.identity, self.components, cards),
            )

    def test_response_marks_unconfirmed_sections_unavailable(self) -> None:
        profile = parse_profile(
            profile_id="example-person",
            profile_urn=PROFILE_URN,
            payloads=(self.identity, self.components, self.cards),
        )
        response = build_profile_response(profile, request_id="req_one")
        self.assertEqual(response.sections.identity.status, "complete")
        self.assertEqual(response.sections.images.status, "complete")
        self.assertEqual(response.sections.about.status, "unavailable")
        self.assertEqual(response.sections.languages.status, "unavailable")
        self.assertEqual(response.profile.experience, [])
        warning_sections = {warning.section for warning in response.warnings}
        self.assertIn("about", warning_sections)
        self.assertIn("languages", warning_sections)

    def test_one_missing_image_is_partial_and_uses_the_largest_safe_artifact(self) -> None:
        identity = copy.deepcopy(self.identity)
        included = identity["included"]
        assert isinstance(included, list)
        assert isinstance(included[0], dict)
        del included[0]["backgroundPicture"]
        profile = parse_profile(
            profile_id="example-person",
            profile_urn=PROFILE_URN,
            payloads=(identity, self.components, self.cards),
        )
        self.assertEqual(profile.images.status, "partial")
        self.assertEqual(profile.images.profile.width, 400)  # type: ignore[union-attr]
        response = build_profile_response(profile, request_id="req_images")
        self.assertEqual(response.sections.images.status, "partial")
        self.assertEqual(response.sections.images.item_count, 1)
        self.assertIn("image_unavailable", {item.code for item in response.warnings})

    def test_request_metadata_is_fresh_not_part_of_domain_snapshot(self) -> None:
        profile = parse_profile(
            profile_id="example-person",
            profile_urn=PROFILE_URN,
            payloads=(self.identity, self.components, self.cards),
        )
        first = build_profile_response(profile, request_id="req_first")
        second = build_profile_response(profile, request_id="req_second")
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertFalse(hasattr(profile, "request_id"))
        self.assertFalse(hasattr(profile, "cache_status"))

    def test_public_schema_is_strict_and_profile_dates_are_partial(self) -> None:
        with self.assertRaises(ValidationError):
            ExperienceItemV1(
                title="Engineer",
                company=None,
                location=None,
                start_date="2026-13",
                end_date=None,
                duration_text=None,
                description=None,
            )
        profile = parse_profile(
            profile_id="example-person",
            profile_urn=PROFILE_URN,
            payloads=(self.identity, self.components, self.cards),
        )
        payload = build_profile_response(profile, request_id="req_strict").model_dump()
        payload["unexpected"] = True
        with self.assertRaises(ValidationError):
            ProfileResponseV1.model_validate(payload)

        with self.assertRaises(ValidationError):
            ImageV1(
                url="https://media.licdn.com/dms/image/synthetic",
                width=0,
                height=100,
            )
        with self.assertRaises(ValidationError):
            SectionStatusV1(status="complete", item_count=-1)

        aware = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
        CacheMetadataV1(stored_at=aware, expires_at=aware)
        with self.assertRaises(ValidationError):
            CacheMetadataV1(
                stored_at=aware,
                expires_at=aware - timedelta(seconds=1),
            )
        with self.assertRaises(ValidationError):
            CacheMetadataV1(
                stored_at=aware.replace(tzinfo=None),
                expires_at=aware.replace(tzinfo=None),
            )


if __name__ == "__main__":
    unittest.main()
