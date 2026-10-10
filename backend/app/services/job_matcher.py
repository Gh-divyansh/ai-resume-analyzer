import re
from typing import Any


MAX_LIST_ITEMS = 8
PREFERRED_CUES = ("preferred", "nice to have", "bonus", "plus", "desired", "ideally")
SENIORITY_RANKS = {"junior": 1, "mid": 2, "senior": 3, "lead": 4, "staff": 5}
TITLE_STOP_WORDS = {"a", "an", "and", "at", "for", "in", "of", "or", "the", "to", "with", "developer", "engineer", "manager", "specialist"}
RESPONSIBILITY_TERMS = {
    "Build": ("build", "built", "develop", "developed", "create", "created", "implement", "implemented"),
    "Design": ("design", "architect"),
    "Lead": ("lead", "mentor"),
    "Deploy": ("deploy", "release", "ship"),
    "Optimize": ("optimize", "optimized", "improve", "improved", "performance"),
    "Integrate": ("integrate", "integration"),
    "Maintain": ("maintain", "support"),
    "Collaborate": ("collaborate", "cross-functional", "stakeholder"),
    "Analyze": ("analyze", "analysis", "measure"),
}

# Canonical names and controlled, explainable variations used in both resumes and JDs.
SKILL_ALIASES = {
    "Python": ("python",), "JavaScript": ("javascript", "java script", "js"),
    "TypeScript": ("typescript", "type script", "ts"), "React": ("react", "react.js", "reactjs"),
    "Node.js": ("node", "node.js", "nodejs"), "Next.js": ("next", "next.js", "nextjs"),
    "FastAPI": ("fastapi", "fast api"), "Django": ("django",), "Flask": ("flask",),
    "Java": ("java",), "C++": ("c++",), "C#": ("c#", "c sharp"),
    "SQL": ("sql", "mysql", "postgresql", "postgres", "sqlite"),
    "MongoDB": ("mongodb", "mongo db", "mongo"), "Redis": ("redis",),
    "REST APIs": ("rest api", "rest apis", "restful", "restful api", "restful apis"),
    "GraphQL": ("graphql", "graph ql"), "Docker": ("docker", "containers", "containerization"),
    "Kubernetes": ("kubernetes", "k8s"), "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",), "GCP": ("gcp", "google cloud"),
    "Git": ("git", "github", "gitlab", "bitbucket"),
    "CI/CD": ("ci/cd", "cicd", "continuous integration", "continuous delivery"),
    "Linux": ("linux",), "Terraform": ("terraform",), "Pandas": ("pandas",),
    "NumPy": ("numpy",), "Machine Learning": ("machine learning", "ml"),
    "Data Analysis": ("data analysis", "data analytics"), "Figma": ("figma",),
    "Agile": ("agile", "scrum"), "Shopify": ("shopify",),
}


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(phrase.lower()) + r"(?!\w)", text.lower()))


def _skills_in_text(text: str) -> set[str]:
    return {name for name, aliases in SKILL_ALIASES.items() if any(_contains_phrase(text, alias) for alias in aliases)}


def _responsibilities_in_text(text: str) -> set[str]:
    return {name for name, aliases in RESPONSIBILITY_TERMS.items() if any(_contains_phrase(text, alias) for alias in aliases)}


def _resume_text(resume_data: dict) -> str:
    parts = [_as_text(resume_data.get("title")), _as_text(resume_data.get("summary"))]
    parts.extend(_as_text(skill) for skill in _as_list(resume_data.get("skills")))
    for experience in _as_list(resume_data.get("experience")):
        if isinstance(experience, dict):
            parts.extend([_as_text(experience.get("company")), _as_text(experience.get("role")), _as_text(experience.get("duration"))])
            parts.extend(_as_text(item) for item in _as_list(experience.get("responsibilities")))
    for project in _as_list(resume_data.get("projects")):
        if isinstance(project, dict):
            parts.extend([_as_text(project.get("name")), _as_text(project.get("description"))])
    return " ".join(part for part in parts if part)


def _jd_segments(job_description: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"[\n.;]+", job_description) if segment.strip()]


def _classify_skill_requirements(job_description: str) -> tuple[set[str], set[str]]:
    required: set[str] = set()
    preferred: set[str] = set()
    for segment in _jd_segments(job_description):
        skills = _skills_in_text(segment)
        if any(cue in segment.lower() for cue in PREFERRED_CUES):
            preferred.update(skills)
        else:
            required.update(skills)
    return required, preferred - required


def _experience_requirements(job_description: str) -> list[tuple[str, int]]:
    requirements: list[tuple[str, int]] = []
    pattern = re.compile(r"(\d+)\s*\+?\s*years?(?:\s+of)?\s+([a-zA-Z0-9.+# /-]+?)\s+experience", re.IGNORECASE)
    for match in pattern.finditer(job_description):
        years = int(match.group(1))
        skills = _skills_in_text(match.group(2))
        requirements.extend((skill, years) for skill in skills)
    return list(dict.fromkeys(requirements))


def _seniority_requirement(text: str) -> str | None:
    lowered = text.lower()
    for level in ("staff", "lead", "senior", "mid", "junior"):
        if _contains_phrase(lowered, level) or (level == "mid" and "mid-level" in lowered):
            return level
    return None


def _title_alignment_score(title: str, job_description: str) -> int:
    title_words = {word for word in re.findall(r"[a-zA-Z]{3,}", title.lower()) if word not in TITLE_STOP_WORDS}
    if not title_words:
        return 0
    jd_words = set(re.findall(r"[a-zA-Z]{3,}", job_description.lower()))
    return round(10 * len(title_words & jd_words) / len(title_words))


def _duration_years(duration: str) -> int:
    match = re.search(r"\b(19\d{2}|20\d{2})\s*(?:-|–|to)\s*(19\d{2}|20\d{2})\b", duration)
    if not match:
        return 0
    return max(int(match.group(2)) - int(match.group(1)), 0)


def _experience_evidence(resume_data: dict, skills: set[str], responsibilities: set[str]) -> tuple[list[str], set[str], set[str], dict[str, int]]:
    evidence: list[str] = []
    evidenced_skills: set[str] = set()
    evidenced_responsibilities: set[str] = set()
    skill_years: dict[str, int] = {}

    for experience in _as_list(resume_data.get("experience")):
        if not isinstance(experience, dict):
            continue
        text = " ".join([_as_text(experience.get("role")), _as_text(experience.get("company")), *(_as_text(item) for item in _as_list(experience.get("responsibilities")))])
        found_skills = _skills_in_text(text) & skills
        found_responsibilities = _responsibilities_in_text(text) & responsibilities
        if found_skills or found_responsibilities:
            role = _as_text(experience.get("role")) or "Experience entry"
            company = _as_text(experience.get("company"))
            label = f"{role} at {company}" if company else role
            terms = sorted(found_skills | found_responsibilities)
            evidence.append(f"{label}: {', '.join(terms)}.")
            evidenced_skills.update(found_skills)
            evidenced_responsibilities.update(found_responsibilities)
            years = _duration_years(_as_text(experience.get("duration")))
            for skill in found_skills:
                skill_years[skill] = skill_years.get(skill, 0) + years

    for project in _as_list(resume_data.get("projects")):
        if not isinstance(project, dict):
            continue
        text = " ".join([_as_text(project.get("name")), _as_text(project.get("description"))])
        found_skills = _skills_in_text(text) & skills
        found_responsibilities = _responsibilities_in_text(text) & responsibilities
        if found_skills or found_responsibilities:
            name = _as_text(project.get("name")) or "Project"
            terms = sorted(found_skills | found_responsibilities)
            evidence.append(f"Project: {name}: {', '.join(terms)}.")
            evidenced_skills.update(found_skills)
            evidenced_responsibilities.update(found_responsibilities)

    return evidence[:MAX_LIST_ITEMS], evidenced_skills, evidenced_responsibilities, skill_years


def _seniority_score(resume_data: dict, required_level: str | None) -> int:
    if not required_level:
        return 0
    title_text = " ".join([_as_text(resume_data.get("title")), *(_as_text(item.get("role")) for item in _as_list(resume_data.get("experience")) if isinstance(item, dict))]).lower()
    candidate_level = _seniority_requirement(title_text)
    if candidate_level and SENIORITY_RANKS[candidate_level] >= SENIORITY_RANKS[required_level]:
        return 10
    return 0


def _recommendations(
    missing_required_skills: list[str],
    missing_preferred_skills: list[str],
    experience_gaps: list[str],
    seniority_gap: bool,
    responsibility_gap: bool,
    keyword_gap: bool,
) -> list[str]:
    """Prioritize remedies for the most important documented alignment gaps."""
    recommendations = [
        f"Prioritize the required skill {skill}; add it only if you have hands-on experience and supporting evidence."
        for skill in missing_required_skills[:3]
    ]
    if experience_gaps:
        recommendations.append("Add accurate dates and role bullets that substantiate the experience required by the job description.")
    if seniority_gap:
        recommendations.append("Tailor the headline only when your documented seniority accurately supports the role.")
    if keyword_gap:
        recommendations.append("Where accurate, use the job's relevant terms in the skills, experience, or project evidence already on your resume.")
    if responsibility_gap:
        recommendations.append("Add concise bullets that demonstrate the job responsibilities you already perform.")
    recommendations.extend(
        f"If relevant and supported, document the preferred skill {skill}."
        for skill in missing_preferred_skills[:2]
    )
    return recommendations[:MAX_LIST_ITEMS]


def match_resume_to_job(resume_data: dict, job_description: str) -> dict:
    """Deterministically compare structured resume evidence with a job description."""
    if not isinstance(resume_data, dict):
        raise ValueError("Resume data must be an object.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise ValueError("Job description is required.")

    job_description = job_description.strip()
    required_skills, preferred_skills = _classify_skill_requirements(job_description)
    all_job_skills = required_skills | preferred_skills
    documented_skills = _skills_in_text(_resume_text(resume_data))
    matched_skills = sorted(all_job_skills & documented_skills)
    missing_skills = sorted(all_job_skills - documented_skills)
    missing_required_skills = sorted(required_skills - documented_skills)
    missing_preferred_skills = sorted(preferred_skills - documented_skills)
    job_responsibilities = _responsibilities_in_text(job_description)
    matching_experience, evidenced_skills, evidenced_responsibilities, skill_years = _experience_evidence(resume_data, all_job_skills, job_responsibilities)
    experience_requirements = _experience_requirements(job_description)
    experience_gaps = [f"The resume does not support {years}+ years of {skill} experience." for skill, years in experience_requirements if skill_years.get(skill, 0) < years]
    met_experience = len(experience_requirements) - len(experience_gaps)
    required_level = _seniority_requirement(job_description)

    skill_weight_total = 3 * len(required_skills) + len(preferred_skills)
    skill_weight_matched = 3 * len(required_skills & documented_skills) + len(preferred_skills & documented_skills)
    skills_score = round(45 * skill_weight_matched / skill_weight_total) if skill_weight_total else 0
    experience_score = round(20 * met_experience / len(experience_requirements)) if experience_requirements else 0
    responsibilities_score = round(15 * len(evidenced_responsibilities) / len(job_responsibilities)) if job_responsibilities else 0
    seniority_score = _seniority_score(resume_data, required_level)
    important_keywords = {f"skill:{skill}" for skill in all_job_skills} | {f"responsibility:{term}" for term in job_responsibilities}
    matched_keywords = {f"skill:{skill}" for skill in all_job_skills & documented_skills} | {f"responsibility:{term}" for term in job_responsibilities & evidenced_responsibilities}
    keyword_score = round(10 * len(matched_keywords) / len(important_keywords)) if important_keywords else 0
    keyword_percentage = round(100 * len(matched_keywords) / len(important_keywords)) if important_keywords else 0
    title_score = _title_alignment_score(_as_text(resume_data.get("title")), job_description)
    score_breakdown = {"skills": skills_score, "experience": experience_score, "responsibilities": responsibilities_score, "seniority": seniority_score, "keywords": keyword_score}
    match_score = min(sum(score_breakdown.values()), 100)

    requirements_required = sorted(required_skills) + [f"{years}+ years {skill} experience" for skill, years in experience_requirements]
    if required_level:
        requirements_required.append(f"{required_level.title()}-level role")
    gaps = [f"The resume does not document {skill}." for skill in missing_skills]
    gaps.extend(experience_gaps)
    if required_level and seniority_score == 0:
        gaps.append(f"The resume does not document the required {required_level}-level role.")
    if job_responsibilities - evidenced_responsibilities:
        gaps.append("Some recognized job responsibilities are not evidenced in experience or projects.")
    if not important_keywords:
        gaps.append("No supported ATS keywords were identified in the job description.")

    legacy_result = {
        "match_score": match_score,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "matching_experience": matching_experience,
        "gaps": gaps[:MAX_LIST_ITEMS],
        "recommendations": _recommendations(
            missing_required_skills,
            missing_preferred_skills,
            experience_gaps,
            bool(required_level and seniority_score == 0),
            bool(job_responsibilities - evidenced_responsibilities),
            bool(important_keywords - matched_keywords),
        ),
        "score_breakdown": score_breakdown,
        "keyword_coverage": {"matched": len(matched_keywords), "total": len(important_keywords), "percentage": keyword_percentage, "missing_keywords": sorted(important_keywords - matched_keywords)},
        "requirements": {"required": requirements_required, "preferred": sorted(preferred_skills)},
        "title_alignment": title_score,
    }
    # Runtime import avoids a compatibility-layer import cycle. This layer is
    # a no-op for technical-only JDs and all inactive domain packs.
    from app.services.active_domain_matcher import apply_active_domain_packs
    return apply_active_domain_packs(legacy_result, resume_data, job_description)
