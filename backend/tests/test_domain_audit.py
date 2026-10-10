import json
import unittest
from pathlib import Path

from app.services.job_matcher import match_resume_to_job
from app.services.resume_analyzer import _calculate_score
from app.services.resume_optimizer import generate_resume_optimizations


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "domain_audit.json"


class DomainAuditFixtureTests(unittest.TestCase):
    def test_cross_domain_fixtures_run_deterministically_through_current_services(self):
        fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(fixtures), 15)
        self.assertEqual(
            {fixture["domain"] for fixture in fixtures},
            {
                "Software Developer", "Shopify Developer", "Registered Nurse", "Teacher", "Accountant",
                "Marketing Manager", "Sales Manager", "HR Manager", "Graphic/UI Designer", "Project Manager",
                "Civil Engineer", "Chef", "Lawyer", "Customer Service Professional", "Electrician",
            },
        )

        for fixture in fixtures:
            resume = fixture["resume"]
            job_description = fixture["job_description"]
            first_match = match_resume_to_job(resume, job_description)
            second_match = match_resume_to_job(resume, job_description)
            optimizations = generate_resume_optimizations(resume, job_description, first_match)

            self.assertEqual(first_match, second_match, fixture["domain"])
            self.assertGreaterEqual(_calculate_score(resume), 0, fixture["domain"])
            self.assertLessEqual(_calculate_score(resume), 100, fixture["domain"])
            self.assertGreaterEqual(first_match["match_score"], 0, fixture["domain"])
            self.assertLessEqual(first_match["match_score"], 100, fixture["domain"])
            self.assertEqual(
                set(first_match["score_breakdown"]),
                {"skills", "experience", "responsibilities", "seniority", "keywords"},
                fixture["domain"],
            )
            self.assertIsInstance(optimizations["recommendations"], list, fixture["domain"])


if __name__ == "__main__":
    unittest.main()
