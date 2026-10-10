import unittest

from app.services.job_matcher import match_resume_to_job


RESUME = {
    "name": "Test Candidate",
    "title": "React Developer",
    "summary": "Frontend developer building web applications and API integrations.",
    "skills": ["React", "javascript", "Node.js", "REST API", "Git"],
    "experience": [
        {
            "company": "Example Labs",
            "role": "React Developer",
            "duration": "2023 - Present",
            "responsibilities": [
                "Built React.js interfaces that integrated with Node.js REST APIs.",
            ],
        }
    ],
    "education": [],
    "projects": [
        {
            "name": "Customer Portal",
            "description": "Created a React application using JavaScript and REST APIs.",
        }
    ],
}

JOB_DESCRIPTION = """
We need a Senior React.js Engineer with JavaScript, TypeScript, Node.js,
REST APIs, and AWS experience to build customer-facing web applications.
"""


class JobMatcherTests(unittest.TestCase):
    def test_match_is_stable_and_normalizes_skill_variants(self):
        first_result = match_resume_to_job(RESUME, JOB_DESCRIPTION)
        second_result = match_resume_to_job(RESUME, JOB_DESCRIPTION)

        self.assertEqual(first_result, second_result)
        self.assertEqual(first_result["matched_skills"], ["JavaScript", "Node.js", "REST APIs", "React"])
        self.assertEqual(first_result["missing_skills"], ["AWS", "TypeScript"])
        self.assertGreater(first_result["match_score"], 0)
        self.assertLessEqual(first_result["match_score"], 100)
        self.assertTrue(first_result["matching_experience"])

    def test_match_rejects_blank_job_description(self):
        with self.assertRaisesRegex(ValueError, "Job description is required"):
            match_resume_to_job(RESUME, "  ")

    def test_required_skill_has_more_influence_than_preferred_skill(self):
        resume = {**RESUME, "skills": ["AWS"], "experience": [], "projects": []}
        required_aws = match_resume_to_job(resume, "AWS is required. Python is preferred.")
        preferred_aws = match_resume_to_job(resume, "Python is required. AWS is preferred.")

        self.assertGreater(
            required_aws["score_breakdown"]["skills"],
            preferred_aws["score_breakdown"]["skills"],
        )
        self.assertIn("Python", preferred_aws["missing_skills"])

    def test_explicit_years_and_seniority_require_evidence(self):
        supported_resume = {
            **RESUME,
            "title": "Senior Shopify Developer",
            "skills": ["Shopify", "JavaScript"],
            "experience": [
                {
                    "company": "Example Labs",
                    "role": "Senior Shopify Developer",
                    "duration": "2019 - 2024",
                    "responsibilities": ["Built Shopify storefronts and optimized checkout performance."],
                }
            ],
        }
        result = match_resume_to_job(
            supported_resume,
            "Senior Shopify developer with 3+ years Shopify experience. Must build and optimize storefronts.",
        )

        self.assertEqual(result["score_breakdown"]["experience"], 20)
        self.assertEqual(result["score_breakdown"]["seniority"], 10)
        self.assertGreater(result["score_breakdown"]["responsibilities"], 0)
        self.assertFalse(any("3+ years Shopify" in gap for gap in result["gaps"]))

    def test_keyword_coverage_is_deterministic(self):
        result = match_resume_to_job(RESUME, JOB_DESCRIPTION)
        coverage = result["keyword_coverage"]

        self.assertEqual(coverage["percentage"], round(100 * coverage["matched"] / coverage["total"]))
        self.assertIn("skill:AWS", coverage["missing_keywords"])
        self.assertIn("React", result["requirements"]["required"])


if __name__ == "__main__":
    unittest.main()
