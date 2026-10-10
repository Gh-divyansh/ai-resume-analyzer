import unittest
from unittest.mock import patch

from app.services.resume_analyzer import analyze_resume


SAMPLE_RESUME = {
    "name": "Test Candidate",
    "title": "Backend Developer",
    "summary": "Backend developer with experience building reliable web applications and API integrations.",
    "skills": ["Python", "FastAPI", "SQL", "Docker", "Git", "REST APIs"],
    "experience": [
        {
            "company": "Example Labs",
            "role": "Backend Developer",
            "duration": "2023 - Present",
            "responsibilities": [
                "Built REST APIs used by 20 internal users.",
                "Reduced processing time by 35%.",
                "Maintained Docker deployment workflows.",
            ],
        }
    ],
    "education": [
        {
            "degree": "Bachelor of Technology",
            "institution": "Example University",
            "duration": "2019 - 2023",
        }
    ],
    "projects": [
        {
            "name": "Resume Analyzer",
            "description": "Built a FastAPI application that processed 500 resumes.",
        }
    ],
}


class ResumeAnalyzerTests(unittest.TestCase):
    def test_score_is_stable_and_fallback_preserves_schema(self):
        with patch(
            "app.services.resume_analyzer.client.models.generate_content",
            side_effect=RuntimeError("Gemini unavailable"),
        ):
            first_result = analyze_resume(SAMPLE_RESUME)
            second_result = analyze_resume(SAMPLE_RESUME)

        self.assertEqual(first_result["score"], second_result["score"])
        self.assertEqual(
            set(first_result),
            {"score", "strengths", "weaknesses", "suggestions", "missing_skills"},
        )
        self.assertIsInstance(first_result["score"], int)
        self.assertGreaterEqual(first_result["score"], 0)
        self.assertLessEqual(first_result["score"], 100)


if __name__ == "__main__":
    unittest.main()
