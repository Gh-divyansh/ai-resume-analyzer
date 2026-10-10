"""Internal domain-neutral records for future deterministic matching.

These models are intentionally not request/response schemas.  They provide an
auditable representation for packs and offline parity evaluation while the
production matcher continues to use its existing implementation.
"""

from enum import Enum
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RecordCategory(str, Enum):
    role = "role"
    competency = "competency"
    tool = "tool"
    responsibility = "responsibility"
    experience = "experience"
    credential = "credential"
    education = "education"
    achievement = "achievement"
    keyword = "keyword"
    seniority = "seniority"
    domain_knowledge = "domain_knowledge"


class RequirementPriority(str, Enum):
    required = "required"
    preferred = "preferred"


class EvidenceType(str, Enum):
    skill = "skill"
    responsibility = "responsibility"
    experience = "experience"
    credential = "credential"
    education = "education"
    achievement = "achievement"
    keyword = "keyword"
    title = "title"
    domain = "domain"


class EvidenceStrength(str, Enum):
    keyword_mention = "keyword_mention"
    explicit_skill = "explicit_skill"
    direct_responsibility = "direct_responsibility"
    experience_evidence = "experience_evidence"
    credential_evidence = "credential_evidence"
    education_evidence = "education_evidence"
    achievement_evidence = "achievement_evidence"
    title_seniority = "title_seniority"
    domain_evidence = "domain_evidence"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequirementRecord(_StrictModel):
    canonical_id: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    category: RecordCategory
    priority: RequirementPriority
    evidence_type: EvidenceType
    source_text: str = Field(min_length=1)
    pack: str = Field(min_length=1)
    pack_version: str = Field(min_length=1)
    minimum_years: int | None = Field(default=None, ge=0)


class EvidenceRecord(_StrictModel):
    canonical_id: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    category: RecordCategory
    evidence_type: EvidenceType
    strength: EvidenceStrength
    source_text: str = Field(min_length=1)
    source_section: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    documented_years: int = Field(default=0, ge=0)


def normalize_pack_alias(value: str) -> str:
    """Normalize aliases deterministically without changing punctuation."""

    return re.sub(r"\s+", " ", value.casefold()).strip()


class PackConcept(_StrictModel):
    canonical_id: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    category: RecordCategory
    aliases: list[str] = Field(min_length=1)
    evidence_types: list[EvidenceType] = Field(min_length=1)

    @field_validator("canonical_id")
    @classmethod
    def canonical_id_is_normalized(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*", value):
            raise ValueError("canonical_id must be a normalized dotted identifier.")
        return value

    @field_validator("aliases")
    @classmethod
    def aliases_are_normalized_and_unique(cls, aliases: list[str]) -> list[str]:
        if any(not alias for alias in aliases):
            raise ValueError("aliases must be non-empty strings.")
        normalized = [normalize_pack_alias(alias) for alias in aliases]
        if aliases != normalized:
            raise ValueError("aliases must be normalized (casefolded with single spaces).")
        if len(set(normalized)) != len(normalized):
            raise ValueError("aliases must not repeat within a concept.")
        return aliases

    @field_validator("evidence_types")
    @classmethod
    def evidence_types_are_unique(cls, values: list[EvidenceType]) -> list[EvidenceType]:
        if len(set(values)) != len(values):
            raise ValueError("evidence_types must not repeat within a concept.")
        return values


class CompetencyPack(_StrictModel):
    pack_id: str = Field(min_length=3)
    version: str = Field(min_length=1)
    namespace: str = Field(min_length=2)
    concepts: list[PackConcept] = Field(min_length=1)

    @field_validator("pack_id")
    @classmethod
    def pack_id_is_normalized(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9-]*", value):
            raise ValueError("pack_id must contain lowercase letters, digits, and hyphens only.")
        return value

    @field_validator("version")
    @classmethod
    def version_is_positive_integer(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9]\d*", value):
            raise ValueError("version must be a positive integer string.")
        return value

    @field_validator("namespace")
    @classmethod
    def namespace_is_normalized(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError("namespace must be a normalized identifier.")
        return value

    @model_validator(mode="after")
    def references_and_aliases_are_unambiguous(self) -> "CompetencyPack":
        canonical_ids = [concept.canonical_id for concept in self.concepts]
        if len(set(canonical_ids)) != len(canonical_ids):
            raise ValueError("canonical_id values must be unique within a pack.")
        if any(not concept.canonical_id.startswith(f"{self.namespace}.") for concept in self.concepts):
            raise ValueError("each canonical_id must use the pack namespace.")

        alias_owner: dict[str, str] = {}
        for concept in self.concepts:
            for alias in concept.aliases:
                existing = alias_owner.get(alias)
                if existing and existing != concept.canonical_id:
                    raise ValueError(f"alias '{alias}' maps ambiguously to multiple concepts.")
                alias_owner[alias] = concept.canonical_id
        return self
