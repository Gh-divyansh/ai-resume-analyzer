"""Internal schemas for the AI evidence layer of universal matching."""
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequirementPriority(str, Enum):
    required = "required"
    preferred = "preferred"


class RequirementCategory(str, Enum):
    skill = "skill"
    competency = "competency"
    responsibility = "responsibility"
    experience = "experience"
    seniority = "seniority"
    credential = "credential"
    education = "education"
    domain_knowledge = "domain_knowledge"


class EvidenceStrength(str, Enum):
    explicit = "explicit"
    experience = "experience"
    project = "project"
    education = "education"
    keyword_only = "keyword_only"
    inferred = "inferred"
    none = "none"


class UniversalEvidence(_Strict):
    source_section: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    strength: EvidenceStrength
    explanation: str = Field(min_length=1)


class UniversalRequirement(_Strict):
    id: str = Field(min_length=1, pattern=r"[a-z][a-z0-9_-]*")
    label: str = Field(min_length=1)
    category: RequirementCategory
    priority: RequirementPriority
    minimum_years: int | None = Field(default=None, ge=0, le=60)
    evidence: list[UniversalEvidence] = Field(default_factory=list)
    explanation: str = Field(min_length=1)


class UniversalAIAnalysis(_Strict):
    requirements: list[UniversalRequirement] = Field(min_length=1, max_length=40)
    overall_explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_requirement_ids(self):
        identifiers = [requirement.id for requirement in self.requirements]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Requirement IDs must be unique.")
        return self
