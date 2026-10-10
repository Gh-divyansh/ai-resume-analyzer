import json
import re
from typing import Any

from google.genai import types

from app.services.ai_service import client


MAX_ITEMS_PER_SECTION = 5


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _experience_items(resume_data: dict) -> list[dict]:
    return [item for item in _as_list(resume_data.get("experience")) if isinstance(item, dict)]


def _project_items(resume_data: dict) -> list[dict]:
    return [item for item in _as_list(resume_data.get("projects")) if isinstance(item, dict)]


def _education_items(resume_data: dict) -> list[dict]:
    return [item for item in _as_list(resume_data.get("education")) if isinstance(item, dict)]


def _has_quantified_impact(resume_data: dict) -> bool:
    text_parts = [_as_text(resume_data.get("summary"))]
    for experience in _experience_items(resume_data):
        text_parts.extend(_as_text(item) for item in _as_list(experience.get("responsibilities")))
    for project in _project_items(resume_data):
        text_parts.append(_as_text(project.get("description")))

    impact_pattern = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:%|x|k|m|million|thousand|users|clients|customers|projects|days|hours)\b",
        re.IGNORECASE,
    )
    return bool(impact_pattern.search(" ".join(text_parts)))


def _calculate_score(resume_data: dict) -> int:
    """Return a stable 0-100 score from documented resume content."""
    skills = [_as_text(skill) for skill in _as_list(resume_data.get("skills")) if _as_text(skill)]
    experience = _experience_items(resume_data)
    education = _education_items(resume_data)
    projects = _project_items(resume_data)

    name = _as_text(resume_data.get("name"))
    title = _as_text(resume_data.get("title"))
    summary = _as_text(resume_data.get("summary"))
    responsibilities = [
        _as_text(item)
        for role in experience
        for item in _as_list(role.get("responsibilities"))
        if _as_text(item)
    ]
    project_descriptions = [_as_text(project.get("description")) for project in projects]

    # Header and summary: 10 points.
    header_score = (2 if name else 0) + (3 if title else 0) + (5 if len(summary) >= 40 else 0)

    # Skills: 20 points. This measures documented breadth, not claimed proficiency.
    skills_score = min(len(skills) * 2.5, 20)

    # Experience: 30 points for role history, complete entries, detail, and measurable impact.
    experience_count_score = min(len(experience) * 7, 14)
    complete_roles_score = min(
        sum(bool(_as_text(role.get("company"))) and bool(_as_text(role.get("role"))) for role in experience) * 3,
        6,
    )
    responsibility_score = min(len(responsibilities), 6)
    impact_score = 4 if _has_quantified_impact(resume_data) else 0
    experience_score = experience_count_score + complete_roles_score + responsibility_score + impact_score

    # Projects: 15 points for present, described projects and documented impact.
    project_count_score = min(len(projects) * 4, 8)
    project_description_score = min(sum(bool(description) for description in project_descriptions) * 2.5, 5)
    project_impact_score = 2 if any(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|x|k|m)\b", text, re.IGNORECASE) for text in project_descriptions) else 0
    projects_score = project_count_score + project_description_score + project_impact_score

    # Education: 10 points for one or more complete entries.
    complete_education = sum(
        bool(_as_text(item.get("degree"))) and bool(_as_text(item.get("institution")))
        for item in education
    )
    education_score = min(complete_education * 8, 10) + (2 if len(education) > complete_education else 0)

    # Presentation: 15 points for enough detail to make the structure useful to a recruiter.
    presentation_score = (
        (5 if len(summary) >= 80 else 0)
        + (3 if title else 0)
        + (3 if len(responsibilities) >= 3 else 0)
        + (2 if any(project_descriptions) else 0)
        + (2 if len(skills) >= 5 else 0)
    )

    return round(header_score + skills_score + experience_score + projects_score + education_score + presentation_score)


def _fallback_feedback(resume_data: dict) -> dict[str, list[str]]:
    """Create safe, factual feedback if Gemini is unavailable or returns invalid JSON."""
    skills = [_as_text(skill) for skill in _as_list(resume_data.get("skills")) if _as_text(skill)]
    experience = _experience_items(resume_data)
    projects = _project_items(resume_data)
    education = _education_items(resume_data)
    summary = _as_text(resume_data.get("summary"))
    responsibilities = [
        _as_text(item)
        for role in experience
        for item in _as_list(role.get("responsibilities"))
        if _as_text(item)
    ]

    strengths: list[str] = []
    weaknesses: list[str] = []
    suggestions: list[str] = []

    if len(summary) >= 40:
        strengths.append("Includes a professional summary.")
    else:
        weaknesses.append("The professional summary is missing or too brief.")
        suggestions.append("Add a concise summary that states your role, relevant strengths, and target direction.")

    if len(skills) >= 5:
        strengths.append(f"Lists {len(skills)} documented skills.")
    else:
        weaknesses.append("The skills section has limited documented breadth.")
        suggestions.append("List relevant skills you can support with experience, projects, or training.")

    if experience:
        strengths.append(f"Documents {len(experience)} experience entr{'y' if len(experience) == 1 else 'ies'}.")
    else:
        weaknesses.append("No professional experience entries were identified.")
        suggestions.append("Add relevant work, internship, volunteer, or practical experience entries where applicable.")

    if projects:
        strengths.append(f"Includes {len(projects)} project{'s' if len(projects) != 1 else ''}.")
    else:
        weaknesses.append("No projects were identified.")
        suggestions.append("Add relevant projects that demonstrate skills you already have.")

    if education:
        strengths.append("Includes education information.")
    else:
        weaknesses.append("No education information was identified.")
        suggestions.append("Add education or relevant certifications if they support your application.")

    if not _has_quantified_impact(resume_data):
        weaknesses.append("The resume does not show clearly quantified outcomes.")
        suggestions.append("Where accurate, add metrics that show the scope or outcome of your work.")

    if not responsibilities:
        weaknesses.append("Experience entries have little responsibility or achievement detail.")
        suggestions.append("Add concise bullets that explain responsibilities and outcomes for each role.")

    return {
        "strengths": strengths[:MAX_ITEMS_PER_SECTION],
        "weaknesses": weaknesses[:MAX_ITEMS_PER_SECTION],
        "suggestions": suggestions[:MAX_ITEMS_PER_SECTION],
        "missing_skills": [],
    }


def _normalise_feedback(value: Any, fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return fallback

    feedback: dict[str, list[str]] = {}
    for key in ("strengths", "weaknesses", "suggestions", "missing_skills"):
        items = value.get(key)
        if not isinstance(items, list):
            feedback[key] = fallback[key]
            continue

        cleaned = [_as_text(item) for item in items if _as_text(item)]
        feedback[key] = cleaned[:MAX_ITEMS_PER_SECTION] or fallback[key]

    return feedback


def _generate_qualitative_feedback(resume_data: dict, score: int) -> dict[str, list[str]]:
    fallback = _fallback_feedback(resume_data)
    prompt = f"""
You are an expert technical recruiter reviewing structured resume data.

The numeric resume score has already been calculated by deterministic rules. Do not score, rescore, or mention a different score.

Return only valid JSON with exactly these keys:
{{
  "strengths": [],
  "weaknesses": [],
  "suggestions": [],
  "missing_skills": []
}}

Rules:
- Base every observation only on the provided resume data.
- Do not invent work history, achievements, skills, qualifications, or target jobs.
- Provide up to 5 concise, specific items per list. Empty lists are allowed.
- Suggestions must be practical and must not encourage unsupported claims.
- Recommend missing skills only when they are a reasonable extension of documented technologies or career direction; otherwise return an empty list.

Deterministic score: {score}/100
Resume data:
{json.dumps(resume_data, indent=2, default=str)}
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        parsed = response.parsed if response.parsed else json.loads(response.text or "{}")
        return _normalise_feedback(parsed, fallback)
    except Exception as error:
        print("Qualitative resume feedback error:", error)
        return fallback


def analyze_resume(resume_data: dict) -> dict:
    """Synchronously score documented resume content and add qualitative feedback."""
    if not isinstance(resume_data, dict):
        raise ValueError("Resume data must be an object.")

    score = _calculate_score(resume_data)
    feedback = _generate_qualitative_feedback(resume_data, score)

    return {"score": score, **feedback}
