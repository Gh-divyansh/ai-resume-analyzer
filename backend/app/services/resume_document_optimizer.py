"""Grounded JD-specific resume wording optimization."""
import json
from copy import deepcopy
from google.genai import types
from app.services.ai_service import client
from app.services.bullet_improver import _validate_generated_bullet, BulletImprovementGenerationError

class ResumeDocumentOptimizationError(RuntimeError): pass

def optimize_resume_for_job(resume: dict, job_description: str, job_match: dict) -> tuple[dict, list[dict], list[str]]:
    """Create a separate grounded JD-specific resume version.

    A rejected generated rewrite is a safety outcome, not a failed request. If
    none pass factual validation, the function returns an unchanged copy so a
    caller can still produce a safe document and surface the actual JD gaps.
    """
    if not isinstance(resume, dict):
        raise ResumeDocumentOptimizationError("Resume data is required.")
    if not isinstance(job_description, str) or not job_description.strip():
        raise ResumeDocumentOptimizationError("A job description is required before optimizing a resume.")
    source_bullets = [b for e in resume.get("experience", []) for b in e.get("responsibilities", [])] + [p.get("description", "") for p in resume.get("projects", [])]
    prompt = f'''Return JSON only: {{"rewrites":[{{"original":"","improved":"","reason":""}}]}}. Rewrite only documented bullets for this job description. Every original must be copied exactly from the resume. Preserve every factual claim; do not add skills, dates, employers, metrics, credentials, responsibilities, or achievements. Do not output rewrites for unsupported JD requirements.\nResume: {json.dumps(resume)}\nJD: {job_description}'''
    try:
        response = client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0))
        payload = response.parsed if response.parsed is not None else json.loads(response.text or "")
        rewrites = payload.get("rewrites", []) if isinstance(payload, dict) else []
        if not isinstance(rewrites, list): raise ValueError()
    except Exception as error:
        raise ResumeDocumentOptimizationError("Optimization generation is unavailable.") from error
    optimized = deepcopy(resume); accepted=[]; seen=set()
    for rewrite in rewrites:
        original, improved = rewrite.get("original"), rewrite.get("improved")
        if not isinstance(original, str) or not isinstance(improved, str) or original not in source_bullets or original in seen: continue
        try: _validate_generated_bullet(original, improved)
        except BulletImprovementGenerationError: continue
        for entry in optimized.get("experience", []): entry["responsibilities"] = [improved if item == original else item for item in entry.get("responsibilities", [])]
        for project in optimized.get("projects", []):
            if project.get("description") == original: project["description"] = improved
        seen.add(original); accepted.append({"original": original, "improved": improved, "reason": str(rewrite.get("reason") or "Improves clarity while preserving documented facts.")})
    unsupported = list(dict.fromkeys(job_match.get("missing_skills", []) + job_match.get("gaps", [])))[:12]
    return optimized, accepted, unsupported
