"""Tolerant normalized-JSON parser for the proven three-response flow."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from tross_linkedin_api.domain.profile import (
    DomainProfile,
    DomainSection,
    FieldValue,
    Identity,
    ParserMetadata,
    ParserWarning,
    ProfileImage,
    ProfileImages,
)
from tross_linkedin_api.errors import UpstreamBadResponseError


PARSER_VERSION = "spike0b-v1"
_PROFILE_URN = re.compile(r"urn:li:fsd_profile:[A-Za-z0-9_-]{1,256}")
_UNCONFIRMED_SECTIONS = (
    "experience",
    "education",
    "skills",
    "certifications",
)


def extract_profile_urn(
    payload: Mapping[str, Any], *, expected_profile_id: str
) -> str:
    """Extract the one root-referenced profile matching the requested identifier."""

    root_profile_urns = {
        urn for urn in _root_element_urns(payload) if _PROFILE_URN.fullmatch(urn)
    }
    matches: set[str] = set()
    for entity in _included_entities(payload):
        urn = _entity_urn(entity)
        public_identifier = _text(entity.get("publicIdentifier"))
        if (
            urn is not None
            and urn in root_profile_urns
            and _PROFILE_URN.fullmatch(urn)
            and public_identifier is not None
            and public_identifier.lower() == expected_profile_id
        ):
            matches.add(urn)
    if len(matches) != 1:
        raise UpstreamBadResponseError()
    return next(iter(matches))


def merge_entities_by_urn(
    payloads: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge repeated normalized entities without discarding richer values."""

    merged: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for entity in _included_entities(payload):
            urn = _entity_urn(entity)
            if urn is None:
                continue
            current = merged.get(urn)
            merged[urn] = (
                dict(entity)
                if current is None
                else _merge_mappings(current, entity)
            )
    return merged


def parse_profile(
    *,
    profile_id: str,
    profile_urn: str,
    payloads: tuple[Mapping[str, Any], ...],
    fetched_at: datetime | None = None,
) -> DomainProfile:
    """Map safely evidenced identity/images and mark unconfirmed sections."""

    if len(payloads) != 3 or not _PROFILE_URN.fullmatch(profile_urn):
        raise UpstreamBadResponseError()
    _validate_profile_correlation(
        payloads,
        profile_urn=profile_urn,
        profile_id=profile_id,
    )
    entities = merge_entities_by_urn(payloads)
    profile_entity = entities.get(profile_urn)
    if profile_entity is None:
        raise UpstreamBadResponseError()
    public_identifier = _text(profile_entity.get("publicIdentifier"))
    if public_identifier is None or public_identifier.lower() != profile_id:
        raise UpstreamBadResponseError()

    first_name = _text(profile_entity.get("firstName"))
    last_name = _text(profile_entity.get("lastName"))
    name = " ".join(part for part in (first_name, last_name) if part).strip()
    if not name:
        raise UpstreamBadResponseError()
    headline = _text(profile_entity.get("headline"))
    location = _profile_location(profile_entity, entities)

    profile_image = _extract_named_image(
        profile_entity,
        ("profilePicture", "profilePictureDisplayImage"),
    )
    background_image = _extract_named_image(
        profile_entity,
        ("backgroundPicture", "backgroundImage", "backgroundPictureDisplayImage"),
    )
    images_status = (
        "complete"
        if profile_image is not None and background_image is not None
        else "partial"
        if profile_image is not None or background_image is not None
        else "unavailable"
    )
    image_warnings = ()
    if images_status != "complete":
        image_warnings = (
            ParserWarning(
                "image_unavailable",
                "images",
                "One or more profile images were not available in the proven responses.",
            ),
        )

    about_warning = ParserWarning(
        "section_unavailable",
        "about",
        "About was not observed in the three proven Spike 0B responses.",
    )
    section_warnings = {
        section: ParserWarning(
            "section_unavailable",
            section,  # type: ignore[arg-type]
            "Value-level mapping is unavailable because Spike 0B retained only "
            "structural signals for this section.",
        )
        for section in _UNCONFIRMED_SECTIONS
    }
    language_warning = ParserWarning(
        "section_unavailable",
        "languages",
        "The generic language signal was not confirmed as a profile language section.",
    )
    all_warnings = (
        about_warning,
        *section_warnings.values(),
        language_warning,
        *image_warnings,
    )
    unavailable_sections = {
        section: DomainSection(status="unavailable", warnings=(warning,))
        for section, warning in section_warnings.items()
    }
    timestamp = fetched_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return DomainProfile(
        canonical_profile_id=profile_id,
        canonical_profile_url=f"https://www.linkedin.com/in/{profile_id}",
        fetched_at=timestamp,
        source="linkedin",
        identity=Identity(name=name, headline=headline, location=location),
        about=FieldValue(None, "unavailable"),
        experience=unavailable_sections["experience"],
        education=unavailable_sections["education"],
        skills=unavailable_sections["skills"],
        certifications=unavailable_sections["certifications"],
        languages=DomainSection(status="unavailable", warnings=(language_warning,)),
        images=ProfileImages(
            profile=profile_image,
            background=background_image,
            status=images_status,
            warnings=image_warnings,
        ),
        parser=ParserMetadata(
            parser_version=PARSER_VERSION,
            schema_fingerprint=_schema_fingerprint(payloads),
            warnings=all_warnings,
            sections_seen=_sections_seen(entities.values()),
        ),
    )


def _included_entities(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    included = payload.get("included")
    if not isinstance(included, list):
        return ()
    return (item for item in included if isinstance(item, Mapping))


def _root_element_urns(payload: Mapping[str, Any]) -> tuple[str, ...]:
    data = payload.get("data")
    nested = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(nested, Mapping):
        return ()
    result = nested.get("identityDashProfilesByMemberIdentity")
    elements = result.get("*elements") if isinstance(result, Mapping) else None
    if elements is None:
        elements = nested.get("*elements")
    if not isinstance(elements, list):
        return ()
    return tuple(item for item in elements if isinstance(item, str))


def _validate_profile_correlation(
    payloads: tuple[Mapping[str, Any], ...],
    *,
    profile_urn: str,
    profile_id: str,
) -> None:
    for payload in payloads:
        matching_entities = tuple(
            entity
            for entity in _included_entities(payload)
            if _entity_urn(entity) == profile_urn
        )
        if not matching_entities:
            raise UpstreamBadResponseError()
        for entity in matching_entities:
            public_identifier = _text(entity.get("publicIdentifier"))
            if (
                public_identifier is not None
                and public_identifier.lower() != profile_id
            ):
                raise UpstreamBadResponseError()


def _entity_urn(entity: Mapping[str, Any]) -> str | None:
    value = entity.get("entityUrn")
    return value if isinstance(value, str) and value.startswith("urn:li:") else None


def _merge_mappings(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, Any]:
    result = dict(left)
    for key, value in right.items():
        if key not in result:
            result[key] = value
        else:
            result[key] = _merge_values(result[key], value)
    return result


def _merge_values(left: Any, right: Any) -> Any:
    if right is None or right == "" or right == [] or right == {}:
        return left
    if left is None or left == "" or left == [] or left == {}:
        return right
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return _merge_mappings(left, right)
    if isinstance(left, list) and isinstance(right, list):
        result = list(left)
        for item in right:
            if item not in result:
                result.append(item)
        return result
    return left


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    if isinstance(value, Mapping):
        for key in ("text", "value"):
            if (text := _text(value.get(key))) is not None:
                return text
    return None


def _profile_location(
    profile: Mapping[str, Any], entities: Mapping[str, Mapping[str, Any]]
) -> str | None:
    for key in ("geoLocationName", "locationName"):
        if (value := _text(profile.get(key))) is not None:
            return value
    reference = profile.get("geoLocation")
    if isinstance(reference, str) and reference in entities:
        location_entity = entities[reference]
        for key in (
            "geoLocationName",
            "locationName",
            "defaultLocalizedName",
            "defaultLocalizedNameWithoutCountryName",
        ):
            if (value := _text(location_entity.get(key))) is not None:
                return value
    return None


def _extract_named_image(
    profile: Mapping[str, Any], names: tuple[str, ...]
) -> ProfileImage | None:
    for name in names:
        value = profile.get(name)
        if isinstance(value, Mapping) and (image := _extract_vector_image(value)):
            return image
    return None


def _extract_vector_image(value: Mapping[str, Any]) -> ProfileImage | None:
    candidates: list[Mapping[str, Any]] = []
    stack: list[Mapping[str, Any]] = [value]
    seen = 0
    while stack and seen < 64:
        current = stack.pop()
        seen += 1
        if isinstance(current.get("rootUrl"), str) and isinstance(
            current.get("artifacts"), list
        ):
            candidates.append(current)
        for child in current.values():
            if isinstance(child, Mapping):
                stack.append(child)
    for candidate in candidates:
        root = candidate.get("rootUrl")
        artifacts = [
            item for item in candidate.get("artifacts", []) if isinstance(item, Mapping)
        ]
        artifacts.sort(key=_artifact_area, reverse=True)
        for artifact in artifacts:
            segment = artifact.get("fileIdentifyingUrlPathSegment")
            if not isinstance(root, str) or not isinstance(segment, str):
                continue
            url = f"{root}{segment}"
            if not _safe_image_url(url):
                continue
            width = _positive_int(artifact.get("width"))
            height = _positive_int(artifact.get("height"))
            return ProfileImage(url=url, width=width, height=height)
    return None


def _artifact_area(artifact: Mapping[str, Any]) -> int:
    width = _positive_int(artifact.get("width")) or 0
    height = _positive_int(artifact.get("height")) or 0
    return width * height


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _safe_image_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and (host == "licdn.com" or host.endswith(".licdn.com"))
        and parsed.username is None
        and parsed.password is None
        and port is None
    )


def _schema_fingerprint(payloads: tuple[Mapping[str, Any], ...]) -> str:
    shapes: list[dict[str, Any]] = []
    for payload in payloads:
        types = sorted(
            str(entity.get("$type"))
            for entity in _included_entities(payload)
            if isinstance(entity.get("$type"), str)
        )
        entity_keys = sorted(
            {
                str(key)
                for entity in _included_entities(payload)
                for key in entity.keys()
            }
        )
        shapes.append(
            {
                "top": sorted(str(key) for key in payload.keys()),
                "types": types,
                "entity_keys": entity_keys,
            }
        )
    encoded = json.dumps(shapes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _sections_seen(entities: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    keys = {str(key).lower() for entity in entities for key in entity.keys()}
    signals = {
        "experience": {"position", "positions", "experience"},
        "education": {"education", "educations"},
        "skills": {"profileskill", "skill", "skills"},
        "certifications": {"certification", "certifications"},
        "languages": {"language", "languages"},
    }
    return tuple(
        section for section, candidates in signals.items() if keys & candidates
    )
