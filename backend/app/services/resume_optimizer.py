"""Deterministic, job-specific resume improvement recommendations.

This service intentionally consumes the job matcher output instead of calculating
another ATS score.  It identifies places where accurate, existing information can
be made easier to find for the target job description.
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas.optimizer import OptimizationRecommendation
from app.services.job_matcher import match_resume_to_job


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _is_experience_gap(gap: str) -> bool:
    return "years of" in gap and "experience" in gap


def _is_seniority_gap(gap: str) -> bool:
    return "-level role" in gap


def _is_responsibility_gap(gap: str) -> bool:
    return "responsibilities" in gap and "evidenced" in gap


def generate_resume_optimizations(
    resume_data: dict,
    job_description: str,
    job_match: dict | None = None,
) -> dict:
    """Return ordered recommendations grounded in a matcher result.

    When callers already have a result from ``/api/resume/match``, providing it
    avoids a duplicate matcher invocation.  Omitting it is supported for direct
    API use and still uses the same deterministic matcher.
    """

    if not isinstance(resume_data, dict):
        raise ValueError("Resume data must be an object.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise ValueError("Job description is required.")
    if job_match is not None and not isinstance(job_match, dict):
        raise ValueError("Job match result must be an object when provided.")

    match_result = job_match if job_match is not None else match_resume_to_job(resume_data, job_description)
    requirements = match_result.get("requirements")
    keyword_coverage = match_result.get("keyword_coverage")

    if not isinstance(requirements, dict) or not isinstance(keyword_coverage, dict):
        raise ValueError("Job match result is missing required ATS detail fields.")

    required = {_normalise(item) for item in _as_list(requirements.get("required")) if _as_text(item)}
    preferred = {_normalise(item) for item in _as_list(requirements.get("preferred")) if _as_text(item)}
    missing_skills = [_as_text(item) for item in _as_list(match_result.get("missing_skills")) if _as_text(item)]
    gaps = [_as_text(item) for item in _as_list(match_result.get("gaps")) if _as_text(item)]
    missing_keywords = [
        _as_text(item) for item in _as_list(keyword_coverage.get("missing_keywords")) if _as_text(item)
    ]

    recommendations: list[tuple[int, OptimizationRecommendation]] = []
    seen: set[tuple[str, str]] = set()

    def add(order: int, recommendation: OptimizationRecommendation) -> None:
        key = (recommendation.category, _normalise(recommendation.issue))
        if key not in seen:
            seen.add(key)
            recommendations.append((order, recommendation))

    # Skills follow the matcher's required/preferred classification exactly.
    for skill in missing_skills:
        normalised_skill = _normalise(skill)
        if normalised_skill in required:
            add(
                10,
                OptimizationRecommendation(
                    priority="high",
                    category="skills",
                    section="Skills and relevant experience/projects",
                    issue=f"The required skill '{skill}' is not documented in the resume.",
                    recommendation=(
                        f"If you have hands-on {skill} experience, add it to Skills and support it with an "
                        "accurate experience or project bullet."
                    ),
                    reason=f"{skill} is classified as required by the target job description.",
                ),
            )
        elif normalised_skill in preferred:
            add(
                60,
                OptimizationRecommendation(
                    priority="low",
                    category="skills",
                    section="Skills and relevant experience/projects",
                    issue=f"The preferred skill '{skill}' is not documented in the resume.",
                    recommendation=(
                        f"If you have hands-on {skill} experience, add it only with truthful supporting evidence."
                    ),
                    reason=f"{skill} is classified as preferred, so it is less important than a required gap.",
                ),
            )

    for gap in gaps:
        if _is_experience_gap(gap):
            add(
                20,
                OptimizationRecommendation(
                    priority="high",
                    category="experience",
                    section="Experience",
                    issue=gap,
                    recommendation=(
                        "If accurate, add complete dates and concise bullets that substantiate the required "
                        "technology experience; do not claim an unsupported duration."
                    ),
                    reason="The target job description has an explicit experience-duration requirement.",
                ),
            )
        elif _is_seniority_gap(gap):
            add(
                30,
                OptimizationRecommendation(
                    priority="high",
                    category="seniority",
                    section="Headline and experience",
                    issue=gap,
                    recommendation=(
                        "Do not change a job title unless it is accurate. Surface the most senior documented role "
                        "and the responsibilities that demonstrate its level."
                    ),
                    reason="The target job description specifies a seniority level not documented in the resume.",
                ),
            )
        elif _is_responsibility_gap(gap):
            add(
                50,
                OptimizationRecommendation(
                    priority="medium",
                    category="responsibilities",
                    section="Experience and projects",
                    issue=gap,
                    recommendation=(
                        "If you performed relevant work, add concise bullets describing the matching responsibility "
                        "and its factual outcome."
                    ),
                    reason="The matcher found recognized job responsibilities without supporting resume evidence.",
                ),
            )

    if missing_keywords:
        display_keywords = ", ".join(item.removeprefix("skill:").removeprefix("responsibility:") for item in missing_keywords)
        add(
            40,
            OptimizationRecommendation(
                priority="medium",
                category="keywords",
                section="Skills, experience, and projects",
                issue=f"Important JD keywords are not evidenced: {display_keywords}.",
                recommendation=(
                    "Where truthful, use these exact job-description terms in the section that documents the "
                    "underlying skill or responsibility; do not add keywords without evidence."
                ),
                reason="These controlled terms are included in the matcher's missing keyword coverage.",
            ),
        )

    summary = _as_text(resume_data.get("summary"))
    if len(summary) < 40 and (required or preferred):
        add(
            70,
            OptimizationRecommendation(
                priority="low",
                category="summary",
                section="Professional summary",
                issue="The resume has no substantive summary tailored to the documented target-job strengths.",
                recommendation=(
                    "Add a short, truthful summary that foregrounds only the skills and experience already "
                    "documented in this resume and relevant to the target job."
                ),
                reason="A clear summary helps recruiters locate existing relevant evidence without implying missing qualifications.",
            ),
        )

    projects = _as_list(resume_data.get("projects"))
    if not projects and any(_is_responsibility_gap(gap) for gap in gaps):
        add(
            80,
            OptimizationRecommendation(
                priority="low",
                category="projects",
                section="Projects",
                issue="No project evidence is documented for the job responsibilities that are currently unmatched.",
                recommendation=(
                    "If you have a relevant project, add it with a truthful description of your contribution, "
                    "tools used, and outcome."
                ),
                reason="A documented project can provide additional evidence for target-job responsibilities.",
            ),
        )

    recommendations.sort(key=lambda item: (PRIORITY_ORDER[item[1].priority], item[0], item[1].issue))
    return {"recommendations": [item.model_dump() for _, item in recommendations]}
