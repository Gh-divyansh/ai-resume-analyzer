"""Gemini-assisted semantic evidence extraction with deterministic ATS scoring.

Gemini identifies bounded requirement/evidence records. This service validates
each citation against ResumeData and calculates every numeric value locally.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from google.genai import types
from pydantic import ValidationError

from app.schemas.universal_match import (
    EvidenceStrength,
    RequirementCategory,
    RequirementPriority,
    UniversalAIAnalysis,
    UniversalRequirement,
)
from app.services.ai_service import client


MODEL = "gemini-3.5-flash-lite"
MAX_ITEMS = 8
MAX_GENERATION_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (1, 2)
GENERATION_SEED = 0
_SCORING_BUCKETS = {
    "skills": {RequirementCategory.skill, RequirementCategory.competency, RequirementCategory.credential, RequirementCategory.education, RequirementCategory.domain_knowledge},
    "responsibilities": {RequirementCategory.responsibility},
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _resume_sections(resume: dict) -> dict[str, list[str]]:
    sections = {"skills": [_text(value) for value in _items(resume.get("skills"))], "summary": [_text(resume.get("summary"))], "experience": [], "projects": [], "education": []}
    for item in _items(resume.get("experience")):
        if isinstance(item, dict):
            sections["experience"].extend([_text(item.get("role")), _text(item.get("company")), _text(item.get("duration")), *[_text(value) for value in _items(item.get("responsibilities"))]])
    for item in _items(resume.get("projects")):
        if isinstance(item, dict):
            sections["projects"].extend([_text(item.get("name")), _text(item.get("description"))])
    for item in _items(resume.get("education")):
        sections["education"].append(" ".join(_text(value) for value in item.values()) if isinstance(item, dict) else _text(item))
    return {name: [value for value in values if value] for name, values in sections.items()}


def _years(resume: dict) -> int:
    total = 0
    for item in _items(resume.get("experience")):
        if isinstance(item, dict):
            match = re.search(r"\b(19\d{2}|20\d{2})\s*(?:-|â€“|to)\s*(19\d{2}|20\d{2})\b", _text(item.get("duration")))
            if match:
                total += max(int(match.group(2)) - int(match.group(1)), 0)
    return total


def _prompt(resume: dict, job_description: str) -> str:
    return f'''You are a cross-domain ATS evidence analyst. Analyze the COMPLETE structured resume and COMPLETE target job description before producing any output. This applies to every profession worldwide.
Return ONLY JSON matching this exact schema:
{{"requirements":[{{"id":"short_id","label":"requirement","category":"skill|competency|responsibility|experience|seniority|credential|education|domain_knowledge","priority":"required|preferred","minimum_years":null,"evidence":[{{"source_section":"skills|experience|projects|education|summary","quote":"exact resume wording","strength":"explicit|experience|project|education|keyword_only|inferred|none","explanation":"why this citation does or does not support the requirement"}}],"explanation":"source-grounded assessment"}}],"overall_explanation":"brief evidence-based summary"}}
Rules: extract every meaningful JD requirement (up to 40), including role/title (use category `domain_knowledge`), competencies/skills, responsibilities, explicit years, seniority, credentials/licenses, education, and domain knowledge. Review the entire JD in source order. Create one independent requirement for every meaningful condition; do not merge a role/title, responsibility, duration, seniority, credential, education requirement, or preferred qualification into another record. Use only one of the exact category values in the schema; never use combined labels such as `role|title`. An explicit seniority level in the JD must be a separate `seniority` requirement. Classify a requirement as preferred only when the JD explicitly signals preferred, optional, bonus, or nice-to-have; otherwise classify it as required. Semantic equivalents may satisfy a requirement only when an exact resume citation supports the underlying work. Preserve exact source quotes and source section. Never invent qualifications, duration, credentials, employers, responsibilities, or achievements. A skill, credential, or license explicitly listed in the resume Skills section is `explicit` evidence, not `keyword_only`. A summary or education keyword mention alone is not practical experience or competency proof. Use keyword_only, inferred, or none when evidence is insufficient. Missing evidence means not documented, not that the candidate lacks it. Return at least one requirement for every non-empty JD. Do not output a numeric score.
ResumeData: {json.dumps(resume, ensure_ascii=False)}
Job description: {job_description}'''


@dataclass(frozen=True)
class GenerationMetadata:
    attempts: int
    retries: int


class UniversalAIGenerationError(RuntimeError):
    def __init__(self, message: str, *, attempts: int, transient: bool, kind: str = "generation"):
        super().__init__(message)
        self.attempts = attempts
        self.transient = transient
        self.kind = kind


def _is_transient_error(error: Exception) -> bool:
    """Bound retries to common transport/service failures, never parse errors."""

    message = str(error).casefold()
    code = str(getattr(error, "code", ""))
    return any(marker in message or marker == code for marker in ("429", "500", "502", "503", "504", "timeout", "timed out", "rate limit", "resource exhausted", "temporarily unavailable", "connection reset", "connection error"))


def _config() -> types.GenerateContentConfig:
    """Use JSON mode with a fixed seed; local Pydantic owns strict validation.

    Gemini's current endpoint rejects the Pydantic schema's `additionalProperties`
    representation, so passing it as `response_schema` makes every request fail.
    We intentionally keep API-level JSON mode and validate the complete payload
    locally before any result can be returned.
    """

    return types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0,
        seed=GENERATION_SEED,
    )


def _parse_analysis(response: Any) -> UniversalAIAnalysis:
    payload = response.parsed if getattr(response, "parsed", None) else json.loads(getattr(response, "text", "") or "")
    return UniversalAIAnalysis.model_validate(payload)


def _format_correction_prompt() -> str:
    return "Your previous response was invalid or incomplete. Return a complete fresh JSON response that exactly follows the supplied schema. Include every meaningful JD requirement, unique valid IDs, every required field, and no prose."


def extract_universal_ai_analysis(resume: dict, job_description: str, *, include_metadata: bool = False):
    prompt = _prompt(resume, job_description)
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(model=MODEL, contents=prompt, config=_config())
            analysis = _parse_analysis(response)
            metadata = GenerationMetadata(attempts=attempt, retries=attempt - 1)
            return (analysis, metadata) if include_metadata else analysis
        except Exception as error:
            transient = _is_transient_error(error)
            format_error = isinstance(error, (json.JSONDecodeError, ValidationError, TypeError, AttributeError))
            if not transient and not format_error:
                raise UniversalAIGenerationError("Gemini generation failed.", attempts=attempt, transient=False) from error
            if attempt == MAX_GENERATION_ATTEMPTS:
                kind = "transport" if transient else "format"
                raise UniversalAIGenerationError("Gemini returned invalid structured analysis." if format_error else "Gemini generation failed.", attempts=attempt, transient=transient, kind=kind) from error
            if transient:
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
            else:
                prompt = f"{_prompt(resume, job_description)}\n\n{_format_correction_prompt()}"
    raise AssertionError("Generation loop must return or raise.")


def _supported(requirement: UniversalRequirement, resume: dict) -> tuple[bool, list[str]]:
    sections = _resume_sections(resume)
    allowed = {"skills", "experience", "projects"}
    if requirement.category is RequirementCategory.education:
        allowed.add("education")
    if requirement.category is RequirementCategory.credential:
        allowed.update({"skills", "experience", "education"})
    valid = []
    for evidence in requirement.evidence:
        quoted = evidence.quote.casefold()
        section_values = sections.get(evidence.source_section, [])
        grounded = bool(quoted) and any(quoted in value.casefold() for value in section_values)
        strong = evidence.strength in {EvidenceStrength.explicit, EvidenceStrength.experience, EvidenceStrength.project, EvidenceStrength.education}
        if grounded and strong and evidence.source_section in allowed:
            valid.append(f"{evidence.source_section}: {evidence.quote}")
    if requirement.minimum_years is not None and _years(resume) < requirement.minimum_years:
        return False, valid
    return bool(valid), valid


def score_universal_analysis(resume: dict, analysis: UniversalAIAnalysis) -> dict:
    assessed = [(requirement, *_supported(requirement, resume)) for requirement in analysis.requirements]
    def component(categories: set[RequirementCategory], points: int) -> int:
        records = [(requirement, supported) for requirement, supported, _ in assessed if requirement.category in categories]
        if not records:
            return 0
        total = sum(3 if requirement.priority is RequirementPriority.required else 1 for requirement, _ in records)
        met = sum(3 if requirement.priority is RequirementPriority.required else 1 for requirement, supported in records if supported)
        return round(points * met / total)
    skills = component(_SCORING_BUCKETS["skills"], 45)
    experience = component({RequirementCategory.experience}, 20)
    responsibilities = component(_SCORING_BUCKETS["responsibilities"], 15)
    seniority = component({RequirementCategory.seniority}, 10)
    keyword_records = [(requirement, supported) for requirement, supported, _ in assessed]
    keywords = round(10 * sum(supported for _, supported in keyword_records) / len(keyword_records)) if keyword_records else 0
    matched = [requirement for requirement, supported, _ in assessed if supported]
    missing = [requirement for requirement, supported, _ in assessed if not supported]
    evidence_lines = {requirement.id: evidence for requirement, _, evidence in assessed}
    return {"match_score": min(skills + experience + responsibilities + seniority + keywords, 100), "score_breakdown": {"skills": skills, "experience": experience, "responsibilities": responsibilities, "seniority": seniority, "keywords": keywords}, "matched": matched, "missing": missing, "evidence": evidence_lines}


def _build_universal_result(resume: dict, analysis: UniversalAIAnalysis) -> dict:
    scored = score_universal_analysis(resume, analysis)
    matched, missing = scored["matched"], scored["missing"]
    required = [item.label for item in analysis.requirements if item.priority is RequirementPriority.required]
    preferred = [item.label for item in analysis.requirements if item.priority is RequirementPriority.preferred]
    matching_evidence = [f"{item.label}: {'; '.join(scored['evidence'][item.id])}." for item in matched if scored["evidence"][item.id]][:MAX_ITEMS]
    missing_keywords = [f"requirement:{item.label}" for item in missing]
    gaps = [f"The resume does not document evidence for {item.label}." for item in missing][:MAX_ITEMS]
    recommendations = [f"If accurate, add source-grounded evidence for the required requirement: {item.label}." for item in missing if item.priority is RequirementPriority.required][:MAX_ITEMS]
    total = len(analysis.requirements)
    return {"match_score": scored["match_score"], "matched_skills": [item.label for item in matched if item.category in _SCORING_BUCKETS["skills"]], "missing_skills": [item.label for item in missing if item.category in _SCORING_BUCKETS["skills"]], "matching_experience": matching_evidence, "gaps": gaps, "recommendations": recommendations, "score_breakdown": scored["score_breakdown"], "keyword_coverage": {"matched": len(matched), "total": total, "percentage": round(100 * len(matched) / total) if total else 0, "missing_keywords": missing_keywords}, "requirements": {"required": required, "preferred": preferred}, "title_alignment": 0, "ai_requirements": [item.model_dump() for item in analysis.requirements], "ai_overall_explanation": analysis.overall_explanation, "matcher": "universal_ai"}


def match_resume_to_job_universal(resume: dict, job_description: str) -> dict:
    if not isinstance(resume, dict):
        raise ValueError("Resume data must be an object.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise ValueError("Job description is required.")
    analysis = extract_universal_ai_analysis(resume, job_description.strip())
    return _build_universal_result(resume, analysis)


def match_resume_to_job_universal_with_metadata(resume: dict, job_description: str) -> tuple[dict, GenerationMetadata]:
    """Runner-only observability without changing the public API response."""
    if not isinstance(resume, dict) or not isinstance(job_description, str) or not job_description.strip():
        raise ValueError("Resume data and job description are required.")
    analysis, metadata = extract_universal_ai_analysis(resume, job_description.strip(), include_metadata=True)
    return _build_universal_result(resume, analysis), metadata
