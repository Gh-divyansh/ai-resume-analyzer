"""Universal eligibility check for uploaded resume/CV documents."""

import json

from google.genai import types

from app.services.ai_service import client


class ResumeClassificationError(RuntimeError):
    """The classification response was unavailable or structurally invalid."""


VALID_LABELS = {"resume", "not_resume", "uncertain"}


def classify_resume_document(text: str) -> str:
    """Return a bounded eligibility label without contributing to any score."""
    prompt = f"""
You are an eligibility classifier for a resume analysis product.

Classify the supplied document as exactly one JSON object:
{{"classification": "resume"}}
{{"classification": "not_resume"}}
{{"classification": "uncertain"}}

Definitions:
- resume: a resume, CV, curriculum vitae, or professional profile describing
  one person's qualifications, work history, education, skills, projects, or
  career background. Accept worldwide professions, student/graduate CVs,
  executive resumes, and region-specific formats. Do not require a particular
  heading, occupation, language style, or section order.
- not_resume: a document whose primary purpose is not a person's career
  profile, including an invoice, receipt, book, article, academic paper,
  assignment, manual, report, standalone certificate, or unrelated document.
- uncertain: the text is too incomplete, corrupted, or ambiguous to establish
  that it is a resume/CV.

Use the document's overall purpose and semantic content. Do not infer a job,
skill, credential, or career fact beyond the text. This decision only controls
eligibility; it must not score the candidate. Return only valid JSON.

Document text:
----------------------------
{text}
----------------------------
"""
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
        )
        payload = response.parsed if response.parsed is not None else json.loads(response.text or "")
        label = payload.get("classification") if isinstance(payload, dict) else None
        if label not in VALID_LABELS:
            raise ResumeClassificationError("Invalid classifier response.")
        return label
    except ResumeClassificationError:
        raise
    except Exception as error:
        raise ResumeClassificationError("Resume eligibility classification is unavailable.") from error
