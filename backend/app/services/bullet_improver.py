"""Safe Gemini-assisted improvement for one documented resume bullet."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from google.genai import types

from app.schemas.bullet_improvement import BulletImprovementResponse
from app.services.ai_service import client
from app.services.bullet_claims import compare_factual_claims
from app.services.job_matcher import (
    SKILL_ALIASES,
    _contains_phrase,
    _skills_in_text,
)


LOGGER = logging.getLogger(__name__)


class BulletImprovementGenerationError(RuntimeError):
    """Raised when Gemini does not return a safe, usable bullet improvement."""


# A number may directly follow a compact version label (``OS2.0``), so a
# word-boundary check is insufficient. This still distinguishes a complete
# numeric value and preserves the same counter-based factual validation.
NUMBER_PATTERN = re.compile(r"(?<![\d.])\d+(?:\.\d+)?")


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _documented_bullets(resume_data: dict) -> list[dict[str, str]]:
    """Return bullets that can be safely improved, with their resume location."""

    bullets: list[dict[str, str]] = []
    for experience in _as_list(resume_data.get("experience")):
        if not isinstance(experience, dict):
            continue
        for responsibility in _as_list(experience.get("responsibilities")):
            text = _as_text(responsibility)
            if text:
                bullets.append(
                    {
                        "text": text,
                        "section": "experience",
                        "company": _as_text(experience.get("company")),
                        "role": _as_text(experience.get("role")),
                    }
                )

    for project in _as_list(resume_data.get("projects")):
        if isinstance(project, dict):
            text = _as_text(project.get("description"))
        else:
            text = _as_text(project)
        if text:
            bullets.append({"text": text, "section": "projects", "company": "", "role": ""})

    return bullets


def _find_documented_bullet(resume_data: dict, bullet: str) -> dict[str, str]:
    normalised_bullet = _normalise(bullet)
    for item in _documented_bullets(resume_data):
        if _normalise(item["text"]) == normalised_bullet:
            return item
    raise ValueError("The bullet must exactly match a documented resume responsibility or project description.")


def _validate_context(context: Any, source: dict[str, str]) -> dict[str, str]:
    if context is None:
        return {}
    if not isinstance(context, dict):
        raise ValueError("Bullet context must be an object when provided.")

    allowed_keys = {"company", "role", "section"}
    unexpected_keys = set(context) - allowed_keys
    if unexpected_keys:
        raise ValueError("Bullet context may contain only company, role, and section.")

    cleaned = {key: _as_text(value) for key, value in context.items() if _as_text(value)}
    if any(not isinstance(value, str) for value in context.values()):
        raise ValueError("Bullet context values must be strings.")
    if cleaned.get("section") and cleaned["section"].casefold() != source["section"]:
        raise ValueError("Bullet context section does not match the documented resume bullet.")
    for key in ("company", "role"):
        if cleaned.get(key) and _normalise(cleaned[key]) != _normalise(source[key]):
            raise ValueError(f"Bullet context {key} does not match the documented resume bullet.")
    return cleaned


def _new_controlled_skills(original: str, improved: str) -> set[str]:
    """Identify recognized technologies newly claimed by a generated bullet."""

    return {
        skill
        for skill, aliases in SKILL_ALIASES.items()
        if any(_contains_phrase(improved, alias) for alias in aliases)
        and not any(_contains_phrase(original, alias) for alias in aliases)
    }


def _keywords_added(original: str, improved: str, job_description: str) -> list[str]:
    """Return only controlled JD skills already present in the source bullet."""

    supported_in_job = _skills_in_text(job_description)
    return sorted(
        skill
        for skill, aliases in SKILL_ALIASES.items()
        if skill in supported_in_job
        and any(_contains_phrase(original, alias) for alias in aliases)
        and any(_contains_phrase(improved, alias) for alias in aliases)
        and not _contains_phrase(original, skill)
        and _contains_phrase(improved, skill)
    )


def _claim_labels(claims: list) -> list[str]:
    """Return bounded validator evidence for server-side rejection diagnostics."""

    return [f"{claim.kind.value}:{claim.value}" for claim in claims]


def _parse_improved_bullet(response: Any) -> str:
    parsed = response.parsed if response.parsed else json.loads(response.text or "{}")
    if not isinstance(parsed, dict):
        raise BulletImprovementGenerationError("Gemini returned an invalid bullet improvement response.")
    improved = _as_text(parsed.get("improved"))
    if not improved:
        raise BulletImprovementGenerationError("Gemini returned an empty improved bullet.")
    return improved


def _repair_wording_only_rejection(original: str, rejected: str, reason: str) -> str:
    """Request one bounded rewrite repair; deterministic validation remains final."""

    prompt = f"""
Revise one rejected resume-bullet rewrite. Return ONLY valid JSON:
{{"improved": ""}}

The source bullet is the sole factual record. Preserve every documented fact,
including numbers, technologies, versions, achievements, credentials, named
entities, and scope. Do not add any new responsibility, object, qualifier, or
metric. Rewrite only the rejected wording so it is a concise natural paraphrase.

Source bullet:
{json.dumps(original)}

Rejected candidate:
{json.dumps(rejected)}

Deterministic validator finding:
{json.dumps(reason)}
"""
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
    )
    return _parse_improved_bullet(response)


def _validate_generated_bullet(original: str, improved: str) -> None:
    if not improved:
        raise BulletImprovementGenerationError("Gemini returned an empty improved bullet.")

    original_numbers = Counter(NUMBER_PATTERN.findall(original))
    improved_numbers = Counter(NUMBER_PATTERN.findall(improved))
    if original_numbers != improved_numbers:
        raise BulletImprovementGenerationError("Generated improvement changed or introduced an unsupported numeric claim.")

    new_skills = _new_controlled_skills(original, improved)
    if new_skills:
        raise BulletImprovementGenerationError(
            "Generated improvement introduced technology not present in the source bullet: "
            + ", ".join(sorted(new_skills))
            + "."
        )

    claim_comparison = compare_factual_claims(original, improved)
    if (
        claim_comparison.missing_claims
        or claim_comparison.introduced_claims
        or claim_comparison.introduced_material_content
    ):
        # Do not log the full resume/JD. These claim labels show why the
        # deterministic guard rejected a generated bullet and make live
        # formatting/model variants diagnosable.
        LOGGER.warning(
            "Bullet factual-validation rejection source_claims=%s generated_claims=%s missing=%s introduced=%s material_content=%s",
            _claim_labels(claim_comparison.source_claims),
            _claim_labels(claim_comparison.generated_claims),
            _claim_labels(claim_comparison.missing_claims),
            _claim_labels(claim_comparison.introduced_claims),
            claim_comparison.introduced_material_content,
        )
    if claim_comparison.missing_claims:
        raise BulletImprovementGenerationError(
            "Generated improvement omitted protected factual claims from the source bullet: "
            + ", ".join(
                f"{claim.kind.value}:{claim.value}"
                for claim in claim_comparison.missing_claims
            )
            + "."
        )

    if claim_comparison.introduced_claims:
        raise BulletImprovementGenerationError(
            "Generated improvement introduced unsupported factual claims: "
            + ", ".join(
                f"{claim.kind.value}:{claim.value}"
                for claim in claim_comparison.introduced_claims
            )
            + "."
        )

    if claim_comparison.introduced_material_content:
        raise BulletImprovementGenerationError(
            "Generated improvement introduced unsupported material factual content: "
            + ", ".join(claim_comparison.introduced_material_content)
            + "."
        )


def _safe_reason(original: str) -> str:
    if NUMBER_PATTERN.search(original):
        return "Clarifies the documented action while preserving the original quantified evidence and meaning."
    return (
        "Clarifies the documented action and ATS wording without adding facts. "
        "If you have a relevant metric, you could add it separately only when it is accurate."
    )


def improve_resume_bullet(
    resume_data: dict,
    job_description: str,
    bullet: str,
    context: dict | None = None,
    job_match: dict | None = None,
    optimization_recommendations: list | None = None,
) -> dict:
    """Improve one existing bullet while treating the source bullet as the fact boundary."""

    if not isinstance(resume_data, dict):
        raise ValueError("Resume data must be an object.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise ValueError("Job description is required.")
    if not isinstance(bullet, str) or not bullet.strip():
        raise ValueError("An existing resume bullet is required.")
    if job_match is not None and not isinstance(job_match, dict):
        raise ValueError("Job match result must be an object when provided.")
    if optimization_recommendations is not None and not isinstance(optimization_recommendations, list):
        raise ValueError("Optimization recommendations must be a list when provided.")

    original = bullet.strip()
    source = _find_documented_bullet(resume_data, original)
    validated_context = _validate_context(context, source)
    prompt_context = {"section": source["section"], **validated_context}

    prompt = f"""
You improve exactly one existing resume bullet for clarity, professional wording, and ATS readability.

Return ONLY valid JSON with exactly this structure:
{{
  "improved": "",
  "reason": "",
  "keywords_added": [],
  "facts_used": []
}}

Non-negotiable accuracy rules:
- The source bullet below is the only factual source for the improved bullet.
- Preserve its meaning. Rephrase it; do not expand it with a new responsibility, technology, employer, project, date, achievement, or metric.
- Do not add a number, percentage, duration, or measurement not already in the source bullet.
- The job description is only a wording guide, never a source of candidate facts.
- Do not add a JD keyword unless it is already explicitly present in the source bullet.
- If the source bullet has no metric, do not fabricate one.

Source bullet:
{json.dumps(original)}

Documented location (not an additional fact source):
{json.dumps(prompt_context)}

Target job description (wording context only):
{json.dumps(job_description.strip())}
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
        )
        improved = _parse_improved_bullet(response)
    except Exception as error:
        LOGGER.exception("Gemini bullet-improvement request failed")
        raise BulletImprovementGenerationError("Failed to generate a bullet improvement.") from error

    try:
        _validate_generated_bullet(original, improved)
    except BulletImprovementGenerationError as initial_error:
        # Gemini is used only to repair wording after a deterministic failure;
        # the repaired result must pass the exact same validator. One retry
        # prevents unbounded API use and never bypasses factual safety. Hard
        # factual violations are never retried: they are not wording issues.
        if "material factual content" not in str(initial_error):
            raise
        LOGGER.info("Retrying rejected bullet wording once with deterministic finding: %s", initial_error)
        try:
            repaired = _repair_wording_only_rejection(original, improved, str(initial_error))
            _validate_generated_bullet(original, repaired)
        except Exception as repair_error:
            LOGGER.warning("Bullet wording repair failed; preserving original rejection: %s", repair_error)
            raise initial_error from repair_error
        improved = repaired
    response_model = BulletImprovementResponse(
        original=original,
        improved=improved,
        reason=_safe_reason(original),
        keywords_added=_keywords_added(original, improved, job_description),
        facts_used=[source["text"]],
    )
    return response_model.model_dump()
