"""Provider-independent canonical profile domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Literal, TypeVar


SectionName = Literal[
    "identity",
    "about",
    "experience",
    "education",
    "skills",
    "certifications",
    "languages",
    "images",
]
SectionState = Literal[
    "complete", "partial", "empty", "unavailable", "parse_error"
]
FieldState = Literal["available", "missing", "unavailable", "parse_error"]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ParserWarning:
    code: str
    section: SectionName
    message: str


@dataclass(frozen=True, slots=True)
class FieldValue(Generic[T]):
    value: T
    status: FieldState
    source_path: str | None = None


@dataclass(frozen=True, slots=True)
class DomainSection(Generic[T]):
    items: tuple[T, ...] = ()
    status: SectionState = "unavailable"
    warnings: tuple[ParserWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class Identity:
    name: str
    headline: str | None
    location: str | None


@dataclass(frozen=True, slots=True)
class ProfileImage:
    url: str
    width: int | None
    height: int | None


@dataclass(frozen=True, slots=True)
class ProfileImages:
    profile: ProfileImage | None
    background: ProfileImage | None
    status: SectionState
    warnings: tuple[ParserWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperienceItem:
    title: str
    company: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    duration_text: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class EducationItem:
    school: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class SkillItem:
    name: str
    endorsement_count: int | None = None


@dataclass(frozen=True, slots=True)
class CertificationItem:
    name: str
    issuer: str | None = None
    issue_date: str | None = None
    expiration_date: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None


@dataclass(frozen=True, slots=True)
class LanguageItem:
    name: str
    proficiency: str | None = None


@dataclass(frozen=True, slots=True)
class ParserMetadata:
    parser_version: str
    schema_fingerprint: str
    warnings: tuple[ParserWarning, ...]
    raw_payload_kind: str = "normalized_json"
    sections_seen: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DomainProfile:
    canonical_profile_id: str
    canonical_profile_url: str
    fetched_at: datetime
    source: Literal["linkedin"]
    identity: Identity
    about: FieldValue[str | None]
    experience: DomainSection[ExperienceItem] = field(default_factory=DomainSection)
    education: DomainSection[EducationItem] = field(default_factory=DomainSection)
    skills: DomainSection[SkillItem] = field(default_factory=DomainSection)
    certifications: DomainSection[CertificationItem] = field(
        default_factory=DomainSection
    )
    languages: DomainSection[LanguageItem] = field(default_factory=DomainSection)
    images: ProfileImages = field(
        default_factory=lambda: ProfileImages(None, None, "unavailable")
    )
    parser: ParserMetadata = field(
        default_factory=lambda: ParserMetadata("unknown", "unknown", ())
    )
