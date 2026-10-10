"""Internal, deterministic factual claims extracted from a resume bullet."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ClaimKind(str, Enum):
    technology = "technology"
    version = "version"
    acronym = "acronym"
    named_entity = "named_entity"
    credential = "credential"
    achievement = "achievement"
    material_responsibility = "material_responsibility"


class BulletClaim(BaseModel):
    """One source-grounded component whose factual meaning must be preserved."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: ClaimKind
    value: str = Field(min_length=1)
    source_text: str = Field(min_length=1)


class ClaimComparison(BaseModel):
    """Deterministic difference between the source and generated bullet claims."""

    source_claims: list[BulletClaim]
    generated_claims: list[BulletClaim]
    missing_claims: list[BulletClaim]
    introduced_claims: list[BulletClaim]
    introduced_material_content: list[str]
