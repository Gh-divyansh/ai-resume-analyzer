"""Inactive record/pack parity harness for the current technology matcher.

Nothing in this module is imported by the API or production matcher.  It exists
only to prove that technology-core@1 represents today's controlled technology
vocabulary before future domain packs are considered.
"""

from __future__ import annotations

from typing import Any

from app.schemas.domain_evidence import (
    CompetencyPack,
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    RequirementPriority,
    RequirementRecord,
)
from app.services.competency_packs import load_technology_core
from app.services.job_matcher import (
    PREFERRED_CUES,
    _as_list,
    _as_text,
    _contains_phrase,
    _jd_segments,
    _resume_text,
    match_resume_to_job,
)


def _concepts_in_text(pack: CompetencyPack, text: str) -> dict[str, Any]:
    return {
        concept.display_name: concept
        for concept in pack.concepts
        if any(_contains_phrase(text, alias) for alias in concept.aliases)
    }


def _classify_technology_requirements(pack: CompetencyPack, job_description: str) -> tuple[dict[str, Any], dict[str, Any]]:
    required: dict[str, Any] = {}
    preferred: dict[str, Any] = {}
    for segment in _jd_segments(job_description):
        concepts = _concepts_in_text(pack, segment)
        destination = preferred if any(cue in segment.lower() for cue in PREFERRED_CUES) else required
        destination.update(concepts)
    for display_name in required:
        preferred.pop(display_name, None)
    return required, preferred


def build_technology_requirement_records(job_description: str, pack: CompetencyPack | None = None) -> list[RequirementRecord]:
    """Create inactive, source-grounded requirement records from technology-core."""

    selected_pack = pack or load_technology_core()
    required, preferred = _classify_technology_requirements(selected_pack, job_description)
    records: list[RequirementRecord] = []
    for priority, concepts in ((RequirementPriority.required, required), (RequirementPriority.preferred, preferred)):
        for display_name, concept in sorted(concepts.items()):
            source_text = next(
                segment for segment in _jd_segments(job_description)
                if display_name in _concepts_in_text(selected_pack, segment)
            )
            records.append(
                RequirementRecord(
                    canonical_id=concept.canonical_id,
                    display_name=display_name,
                    category=concept.category,
                    priority=priority,
                    evidence_type=EvidenceType.skill,
                    source_text=source_text,
                    pack=selected_pack.pack_id,
                    pack_version=selected_pack.version,
                )
            )
    return records


def build_technology_evidence_records(resume_data: dict, pack: CompetencyPack | None = None) -> list[EvidenceRecord]:
    """Represent documented technology mentions with their resume location.

    These records do not claim that a mention independently meets a future
    requirement. Their strength records whether it was listed as a skill or
    found in documented experience/project text.
    """

    selected_pack = pack or load_technology_core()
    records: list[EvidenceRecord] = []

    def add_records(text: str, section: str, reference: str, evidence_type: EvidenceType, strength: EvidenceStrength) -> None:
        for display_name, concept in sorted(_concepts_in_text(selected_pack, text).items()):
            records.append(
                EvidenceRecord(
                    canonical_id=concept.canonical_id,
                    display_name=display_name,
                    category=concept.category,
                    evidence_type=evidence_type,
                    strength=strength,
                    source_text=text,
                    source_section=section,
                    source_reference=reference,
                )
            )

    for index, skill in enumerate(_as_list(resume_data.get("skills"))):
        text = _as_text(skill)
        if text:
            add_records(text, "skills", f"skills[{index}]", EvidenceType.skill, EvidenceStrength.explicit_skill)

    for index, experience in enumerate(_as_list(resume_data.get("experience"))):
        if isinstance(experience, dict):
            text = " ".join(
                [_as_text(experience.get("role")), _as_text(experience.get("company"))]
                + [_as_text(item) for item in _as_list(experience.get("responsibilities"))]
            ).strip()
            if text:
                add_records(text, "experience", f"experience[{index}]", EvidenceType.experience, EvidenceStrength.experience_evidence)

    for index, project in enumerate(_as_list(resume_data.get("projects"))):
        if isinstance(project, dict):
            text = " ".join([_as_text(project.get("name")), _as_text(project.get("description"))]).strip()
        else:
            text = _as_text(project)
        if text:
            add_records(text, "projects", f"projects[{index}]", EvidenceType.experience, EvidenceStrength.direct_responsibility)

    return records


def evaluate_technology_core_parity(resume_data: dict, job_description: str) -> dict:
    """Compare the legacy matcher with an inactive technology-pack projection.

    The legacy result remains the authority. The projection substitutes only
    technology vocabulary discovery with records from technology-core@1 and
    retains the legacy responsibility/seniority components. This is intentional:
    technology-core has no responsibility or seniority entries, so the harness
    verifies exact technology parity rather than becoming a second matcher.
    """

    pack = load_technology_core()
    legacy = match_resume_to_job(resume_data, job_description)
    required, preferred = _classify_technology_requirements(pack, job_description)
    documented = _concepts_in_text(pack, _resume_text(resume_data))
    all_skills = set(required) | set(preferred)
    matched_skills = sorted(all_skills & set(documented))
    missing_skills = sorted(all_skills - set(documented))
    skill_weight_total = 3 * len(required) + len(preferred)
    skill_weight_matched = 3 * len(set(required) & set(documented)) + len(set(preferred) & set(documented))
    skills_score = round(45 * skill_weight_matched / skill_weight_total) if skill_weight_total else 0

    legacy_skill_set = set(legacy["matched_skills"]) | set(legacy["missing_skills"])
    legacy_keyword_coverage = legacy["keyword_coverage"]
    legacy_responsibility_total = legacy_keyword_coverage["total"] - len(legacy_skill_set)
    legacy_responsibility_matched = legacy_keyword_coverage["matched"] - len(legacy["matched_skills"])
    projected_keyword_total = len(all_skills) + legacy_responsibility_total
    projected_keyword_matched = len(matched_skills) + legacy_responsibility_matched
    projected_missing_keywords = sorted(
        [f"skill:{skill}" for skill in missing_skills]
        + [item for item in legacy_keyword_coverage["missing_keywords"] if item.startswith("responsibility:")]
    )
    projected_keyword_percentage = round(100 * projected_keyword_matched / projected_keyword_total) if projected_keyword_total else 0

    projected_breakdown = {**legacy["score_breakdown"], "skills": skills_score}
    projected = {
        "score": min(sum(projected_breakdown.values()), 100),
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "required_skills": sorted(required),
        "preferred_skills": sorted(preferred),
        "keyword_coverage": {
            "matched": projected_keyword_matched,
            "total": projected_keyword_total,
            "percentage": projected_keyword_percentage,
            "missing_keywords": projected_missing_keywords,
        },
    }
    legacy_view = {
        "score": legacy["match_score"],
        "matched_skills": legacy["matched_skills"],
        "missing_skills": legacy["missing_skills"],
        "required_skills": sorted(legacy_skill_set - set(legacy["requirements"]["preferred"])),
        "preferred_skills": legacy["requirements"]["preferred"],
        "keyword_coverage": legacy_keyword_coverage,
    }
    fields = ("score", "matched_skills", "missing_skills", "required_skills", "preferred_skills", "keyword_coverage")
    return {
        "legacy": legacy_view,
        "record_pack_projection": projected,
        "parity": {field: legacy_view[field] == projected[field] for field in fields},
        "record_counts": {
            "requirements": len(build_technology_requirement_records(job_description, pack)),
            "evidence": len(build_technology_evidence_records(resume_data, pack)),
        },
    }
