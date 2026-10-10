"""Add release-approved domain-pack evidence to the legacy ATS result.

The legacy matcher remains authoritative for controlled technology matching.
This module is intentionally additive: if no active-pack requirement appears in
the JD, it returns the legacy response unchanged.
"""
from __future__ import annotations

from app.schemas.domain_evidence import RecordCategory, RequirementPriority
from app.services.competency_packs import load_active_nontechnical_packs
from app.services.domain_pack_evaluator import evaluate_domain_pack_projection


def apply_active_domain_packs(legacy: dict, resume_data: dict, job_description: str) -> dict:
    packs = load_active_nontechnical_packs()
    if not packs:
        return legacy
    projection = evaluate_domain_pack_projection(resume_data, job_description, packs=packs)
    requirements = projection["requirements"]
    if not requirements:
        return legacy

    requirement_by_id = {record.canonical_id: record for record in requirements}
    matched_ids, missing_ids = set(projection["matched"]), set(projection["missing"])
    scored_records = [
        record for record in requirements
        if record.category not in {RecordCategory.role, RecordCategory.seniority, RecordCategory.responsibility}
    ]
    required_domain = {record.canonical_id for record in scored_records if record.priority is RequirementPriority.required}
    preferred_domain = {record.canonical_id for record in scored_records if record.priority is RequirementPriority.preferred}
    matched_domain = matched_ids & (required_domain | preferred_domain)

    # Recalculate only the existing 45-point skills component when an active
    # pack adds a scored requirement. Technical-only requests never reach here.
    legacy_required = (set(legacy["matched_skills"]) | set(legacy["missing_skills"])) - set(legacy["requirements"]["preferred"])
    legacy_preferred = set(legacy["requirements"]["preferred"])
    legacy_matched = set(legacy["matched_skills"])
    total_weight = 3 * (len(legacy_required) + len(required_domain)) + len(legacy_preferred) + len(preferred_domain)
    matched_weight = 3 * (len(legacy_required & legacy_matched) + len(required_domain & matched_domain)) + len(legacy_preferred & legacy_matched) + len(preferred_domain & matched_domain)
    skills_score = round(45 * matched_weight / total_weight) if total_weight else 0

    domain_matched_names = {requirement_by_id[item].display_name for item in matched_domain}
    domain_missing_names = {requirement_by_id[item].display_name for item in missing_ids if item in required_domain | preferred_domain}
    result = {**legacy}
    result["matched_skills"] = sorted(set(legacy["matched_skills"]) | domain_matched_names)
    result["missing_skills"] = sorted(set(legacy["missing_skills"]) | domain_missing_names)
    result["requirements"] = {
        "required": legacy["requirements"]["required"] + [record.display_name for record in scored_records if record.priority is RequirementPriority.required and record.display_name not in legacy["requirements"]["required"]],
        "preferred": legacy["requirements"]["preferred"] + [record.display_name for record in scored_records if record.priority is RequirementPriority.preferred and record.display_name not in legacy["requirements"]["preferred"]],
    }
    breakdown = {**legacy["score_breakdown"], "skills": skills_score}
    result["score_breakdown"] = breakdown
    result["match_score"] = min(sum(breakdown.values()), 100)

    domain_keywords = {f"skill:{requirement_by_id[item].display_name}" for item in required_domain | preferred_domain}
    matched_domain_keywords = {f"skill:{requirement_by_id[item].display_name}" for item in matched_domain}
    old_coverage = legacy["keyword_coverage"]
    old_missing = set(old_coverage["missing_keywords"])
    matched_keywords = old_coverage["matched"] + len(matched_domain_keywords)
    total_keywords = old_coverage["total"] + len(domain_keywords)
    result["keyword_coverage"] = {
        "matched": matched_keywords,
        "total": total_keywords,
        "percentage": round(100 * matched_keywords / total_keywords) if total_keywords else 0,
        "missing_keywords": sorted(old_missing | (domain_keywords - matched_domain_keywords)),
    }
    result["score_breakdown"]["keywords"] = round(10 * matched_keywords / total_keywords) if total_keywords else 0
    result["match_score"] = min(sum(result["score_breakdown"].values()), 100)

    domain_gaps = []
    for item in sorted(missing_ids):
        record = requirement_by_id[item]
        if record.category in {RecordCategory.role, RecordCategory.seniority}:
            continue
        if record.minimum_years is not None:
            domain_gaps.append(f"The resume does not support {record.minimum_years}+ years of {record.display_name} experience.")
        else:
            domain_gaps.append(f"The resume does not document {record.display_name}.")
    result["gaps"] = (legacy["gaps"] + domain_gaps)[:8]
    recommendation = [
        f"Prioritize the required skill {requirement_by_id[item].display_name}; add it only if you have hands-on experience and supporting evidence."
        for item in sorted(missing_ids & required_domain)
    ]
    result["recommendations"] = (recommendation + legacy["recommendations"])[:8]
    if any(record.category is RecordCategory.role and record.canonical_id in matched_ids for record in requirements):
        result["title_alignment"] = max(result["title_alignment"], 10)
    return result
