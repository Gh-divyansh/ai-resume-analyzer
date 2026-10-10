from typing import Literal

from pydantic import BaseModel


class OptimizationRecommendation(BaseModel):
    """A factual, job-specific improvement opportunity for a resume."""

    priority: Literal["high", "medium", "low"]
    category: Literal[
        "skills",
        "experience",
        "keywords",
        "seniority",
        "responsibilities",
        "summary",
        "projects",
        "education",
    ]
    section: str
    issue: str
    recommendation: str
    reason: str


class ResumeOptimizationResponse(BaseModel):
    recommendations: list[OptimizationRecommendation]
