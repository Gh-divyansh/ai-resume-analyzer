"""Inactive deterministic projection for bounded non-technical competency packs.

This module is deliberately not imported by the API matcher.  It provides
auditable records and calibration results before any pack is activated.
"""
from __future__ import annotations

import re
from app.schemas.domain_evidence import EvidenceRecord, EvidenceStrength, EvidenceType, RecordCategory, RequirementPriority, RequirementRecord
from app.services.competency_packs import load_nontechnical_packs
from app.services.job_matcher import PREFERRED_CUES, _as_list, _as_text, _contains_phrase, _duration_years


SENIORITY_LEVELS = ("junior", "mid", "senior")


def _matches(pack, text):
    normalized = re.sub(r"[-/]", " ", text)
    return [
        concept
        for concept in pack.concepts
        if any(_contains_phrase(normalized, re.sub(r"[-/]", " ", alias)) for alias in concept.aliases)
    ]


def _minimum_years(segment: str, concept) -> int | None:
    """Bounded duration extraction, tied to a recognized pack concept only."""

    normalized = re.sub(r"[-/]", " ", segment.lower())
    for alias in concept.aliases:
        pattern = rf"(\d+)\s*\+?\s*years?(?:\s+of)?\s+{re.escape(alias)}(?:\s+experience)?"
        match = re.search(pattern, normalized)
        if match:
            return int(match.group(1))
    return None


def build_domain_requirement_records(job_description: str, packs=None) -> list[RequirementRecord]:
    records = []
    for segment in re.split(r"[\n.;]+", job_description):
        priority = RequirementPriority.preferred if any(cue in segment.lower() for cue in PREFERRED_CUES) else RequirementPriority.required
        for pack in packs or load_nontechnical_packs():
            for concept in _matches(pack, segment):
                records.append(RequirementRecord(canonical_id=concept.canonical_id, display_name=concept.display_name, category=concept.category, priority=priority, evidence_type=concept.evidence_types[0], source_text=segment.strip(), pack=pack.pack_id, pack_version=pack.version, minimum_years=_minimum_years(segment, concept)))
        # Seniority is recognized only as an explicit JD/title level. Ordinary
        # responsibility words such as "lead" or "managed" are not levels.
        for level in SENIORITY_LEVELS:
            if _contains_phrase(segment, level):
                records.append(RequirementRecord(canonical_id=f"seniority.{level}", display_name=level.title(), category=RecordCategory.seniority, priority=priority, evidence_type=EvidenceType.title, source_text=segment.strip(), pack="core-seniority", pack_version="1"))
    # Required wins deterministically when the same concept appears twice.
    required = {record.canonical_id for record in records if record.priority is RequirementPriority.required}
    return [record for record in records if record.priority is RequirementPriority.required or record.canonical_id not in required]


def build_domain_evidence_records(resume_data: dict, packs=None) -> list[EvidenceRecord]:
    records = []
    def add(text, section, reference, evidence_type, strength, documented_years=0, allowed_categories=None):
        for pack in packs or load_nontechnical_packs():
            for concept in _matches(pack, text):
                if allowed_categories is not None and concept.category not in allowed_categories:
                    continue
                records.append(EvidenceRecord(canonical_id=concept.canonical_id, display_name=concept.display_name, category=concept.category, evidence_type=evidence_type, strength=strength, source_text=text, source_section=section, source_reference=reference, documented_years=documented_years))
    for i, value in enumerate(_as_list(resume_data.get("skills"))):
        if _as_text(value): add(_as_text(value), "skills", f"skills[{i}]", EvidenceType.skill, EvidenceStrength.explicit_skill)
    if _as_text(resume_data.get("title")):
        add(_as_text(resume_data["title"]), "header", "title", EvidenceType.title, EvidenceStrength.title_seniority)
        title = _as_text(resume_data["title"])
        for level in SENIORITY_LEVELS:
            if _contains_phrase(title, level):
                records.append(EvidenceRecord(canonical_id=f"seniority.{level}", display_name=level.title(), category=RecordCategory.seniority, evidence_type=EvidenceType.title, strength=EvidenceStrength.title_seniority, source_text=title, source_section="header", source_reference="title"))
    for i, item in enumerate(_as_list(resume_data.get("experience"))):
        if not isinstance(item, dict): continue
        text = " ".join([_as_text(item.get("role")), *(_as_text(x) for x in _as_list(item.get("responsibilities")))]).strip()
        if text: add(text, "experience", f"experience[{i}]", EvidenceType.experience, EvidenceStrength.experience_evidence, _duration_years(_as_text(item.get("duration"))))
    for i, item in enumerate(_as_list(resume_data.get("projects"))):
        text = _as_text(item.get("description")) if isinstance(item, dict) else _as_text(item)
        if text: add(text, "projects", f"projects[{i}]", EvidenceType.responsibility, EvidenceStrength.direct_responsibility)
    for i, item in enumerate(_as_list(resume_data.get("education"))):
        text = " ".join(str(value) for value in item.values()) if isinstance(item, dict) else _as_text(item)
        # Coursework mentioning a competency is not documented competency
        # evidence. Explicit qualifications/education concepts may be retained.
        if text: add(text, "education", f"education[{i}]", EvidenceType.education, EvidenceStrength.education_evidence, allowed_categories={RecordCategory.education, RecordCategory.credential})
    return records


def evaluate_domain_pack_projection(resume_data: dict, job_description: str, packs=None) -> dict:
    """Return inactive domain-pack alignment; no live/API score is changed."""
    requirements = build_domain_requirement_records(job_description, packs=packs)
    evidence = build_domain_evidence_records(resume_data, packs=packs)
    evidence_ids = {item.canonical_id for item in evidence if item.strength is not EvidenceStrength.keyword_mention}
    matched_records = []
    for requirement in requirements:
        supporting = [item for item in evidence if item.canonical_id == requirement.canonical_id]
        if supporting and (requirement.minimum_years is None or max(item.documented_years for item in supporting) >= requirement.minimum_years):
            matched_records.append(requirement)
    matched = {item.canonical_id for item in matched_records}
    all_ids = {item.canonical_id for item in requirements}
    missing = all_ids - matched
    required = {item.canonical_id for item in requirements if item.priority is RequirementPriority.required}
    preferred = {item.canonical_id for item in requirements if item.priority is RequirementPriority.preferred}
    total_weight = 3 * len(required) + len(preferred)
    matched_weight = 3 * len(required & matched) + len(preferred & matched)
    score = round(45 * matched_weight / total_weight) if total_weight else 0
    return {"score": score, "matched": sorted(matched), "missing": sorted(missing), "requirements": requirements, "evidence": evidence}


def evaluate_domain_pack_side_by_side(resume_data: dict, job_description: str) -> dict:
    """Compare the unchanged live matcher with the inactive domain projection."""

    # Import lazily so the legacy matcher can call the production integration
    # layer without a module-import cycle.
    from app.services.job_matcher import match_resume_to_job

    return {
        "legacy": match_resume_to_job(resume_data, job_description),
        "domain_pack_projection": evaluate_domain_pack_projection(resume_data, job_description),
        "active": False,
    }
