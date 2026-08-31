"""Strict versioned profile request and response schemas."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    NonNegativeInt,
    PositiveInt,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from tross_linkedin_api.domain.profile import DomainProfile, ParserWarning
from tross_linkedin_api.schemas.common import (
    NonEmptyStr,
    PartialDate,
    STRICT_MODEL_CONFIG,
)


SectionStatusValue = Literal[
    "complete", "partial", "empty", "unavailable", "parse_error"
]
SectionNameValue = Literal[
    "identity",
    "about",
    "experience",
    "education",
    "skills",
    "certifications",
    "languages",
    "images",
]
WarningCodeValue = Literal[
    "section_unavailable",
    "section_parse_error",
    "profile_visibility_limited",
    "image_unavailable",
    "schema_drift_detected",
]


class ResolveProfileRequest(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    profile_url: StrictStr


class ImageV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    url: StrictStr
    width: PositiveInt | None
    height: PositiveInt | None

    @field_validator("url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if not (
            parsed.scheme == "https"
            and (host == "licdn.com" or host.endswith(".licdn.com"))
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
        ):
            raise ValueError("image URL must use the LinkedIn HTTPS CDN")
        return value


class ImagesV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    profile: ImageV1 | None
    background: ImageV1 | None


class ExperienceItemV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    title: NonEmptyStr
    company: StrictStr | None
    location: StrictStr | None
    start_date: PartialDate | None
    end_date: PartialDate | None
    duration_text: StrictStr | None
    description: StrictStr | None


class EducationItemV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    school: NonEmptyStr
    degree: StrictStr | None
    field_of_study: StrictStr | None
    start_date: PartialDate | None
    end_date: PartialDate | None
    description: StrictStr | None


class SkillItemV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    name: NonEmptyStr
    endorsement_count: StrictInt | None


class CertificationItemV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    name: NonEmptyStr
    issuer: StrictStr | None
    issue_date: PartialDate | None
    expiration_date: PartialDate | None
    credential_id: StrictStr | None
    credential_url: StrictStr | None


class LanguageItemV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    name: NonEmptyStr
    proficiency: StrictStr | None


class ProfileV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    canonical_id: NonEmptyStr
    canonical_url: StrictStr
    name: NonEmptyStr
    headline: StrictStr | None
    location: StrictStr | None
    about: StrictStr | None
    images: ImagesV1
    experience: list[ExperienceItemV1]
    education: list[EducationItemV1]
    skills: list[SkillItemV1]
    certifications: list[CertificationItemV1]
    languages: list[LanguageItemV1]


class SectionStatusV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    status: SectionStatusValue
    item_count: NonNegativeInt | None


class ProfileSectionStatusesV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    identity: SectionStatusV1
    about: SectionStatusV1
    experience: SectionStatusV1
    education: SectionStatusV1
    skills: SectionStatusV1
    certifications: SectionStatusV1
    languages: SectionStatusV1
    images: SectionStatusV1


class ResponseWarningV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    code: WarningCodeValue
    section: SectionNameValue
    message: StrictStr


class CacheMetadataV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    stored_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> CacheMetadataV1:
        if self.expires_at < self.stored_at:
            raise ValueError("cache expiration cannot precede storage time")
        return self


class ProfileResponseV1(BaseModel):
    model_config = STRICT_MODEL_CONFIG

    api_version: Literal["v1"]
    request_id: NonEmptyStr
    profile: ProfileV1
    sections: ProfileSectionStatusesV1
    warnings: list[ResponseWarningV1]
    cache: CacheMetadataV1
    fetched_at: AwareDatetime


def build_profile_response(
    profile: DomainProfile,
    *,
    request_id: str,
) -> ProfileResponseV1:
    """Build a fresh request envelope from request-independent domain data."""

    warnings = _unique_warnings(
        profile.parser.warnings
        + profile.experience.warnings
        + profile.education.warnings
        + profile.skills.warnings
        + profile.certifications.warnings
        + profile.languages.warnings
        + profile.images.warnings
    )
    image_count = sum(
        image is not None for image in (profile.images.profile, profile.images.background)
    )
    # Caching is intentionally deferred. Equal timestamps express an immediately
    # expired miss while preserving the frozen v1 response shape.
    cache_metadata = CacheMetadataV1(
        stored_at=profile.fetched_at,
        expires_at=profile.fetched_at,
    )
    return ProfileResponseV1(
        api_version="v1",
        request_id=request_id,
        profile=ProfileV1(
            canonical_id=profile.canonical_profile_id,
            canonical_url=profile.canonical_profile_url,
            name=profile.identity.name,
            headline=profile.identity.headline,
            location=profile.identity.location,
            about=profile.about.value,
            images=ImagesV1(
                profile=_image_model(profile.images.profile),
                background=_image_model(profile.images.background),
            ),
            experience=[
                ExperienceItemV1(**asdict(item)) for item in profile.experience.items
            ],
            education=[
                EducationItemV1(**asdict(item)) for item in profile.education.items
            ],
            skills=[SkillItemV1(**asdict(item)) for item in profile.skills.items],
            certifications=[
                CertificationItemV1(**asdict(item))
                for item in profile.certifications.items
            ],
            languages=[
                LanguageItemV1(**asdict(item)) for item in profile.languages.items
            ],
        ),
        sections=ProfileSectionStatusesV1(
            identity=SectionStatusV1(status="complete", item_count=None),
            about=SectionStatusV1(status=_about_status(profile), item_count=None),
            experience=SectionStatusV1(
                status=profile.experience.status,
                item_count=len(profile.experience.items),
            ),
            education=SectionStatusV1(
                status=profile.education.status,
                item_count=len(profile.education.items),
            ),
            skills=SectionStatusV1(
                status=profile.skills.status,
                item_count=len(profile.skills.items),
            ),
            certifications=SectionStatusV1(
                status=profile.certifications.status,
                item_count=len(profile.certifications.items),
            ),
            languages=SectionStatusV1(
                status=profile.languages.status,
                item_count=len(profile.languages.items),
            ),
            images=SectionStatusV1(
                status=profile.images.status,
                item_count=image_count,
            ),
        ),
        warnings=[
            ResponseWarningV1(
                code=warning.code,
                section=warning.section,
                message=warning.message,
            )
            for warning in warnings
        ],
        cache=cache_metadata,
        fetched_at=profile.fetched_at,
    )


def _image_model(image: object) -> ImageV1 | None:
    if image is None:
        return None
    return ImageV1(
        url=getattr(image, "url"),
        width=getattr(image, "width"),
        height=getattr(image, "height"),
    )


def _about_status(profile: DomainProfile) -> SectionStatusValue:
    return {
        "available": "complete",
        "missing": "empty",
        "unavailable": "unavailable",
        "parse_error": "parse_error",
    }[profile.about.status]


def _unique_warnings(
    warnings: tuple[ParserWarning, ...],
) -> tuple[ParserWarning, ...]:
    result: list[ParserWarning] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning.code, warning.section)
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return tuple(result)
