import json
import unittest
from pathlib import Path

from app.services.job_matcher import match_resume_to_job


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


class MatchCalibrationTests(unittest.TestCase):
    def test_representative_pairs_produce_stable_alignment_order(self):
        strong = load_fixture("strong_match")
        medium = load_fixture("medium_match")
        weak = load_fixture("weak_match")

        strong_result = match_resume_to_job(strong["resume"], strong["job_description"])
        self.assertEqual(strong_result, match_resume_to_job(strong["resume"], strong["job_description"]))
        medium_result = match_resume_to_job(medium["resume"], medium["job_description"])
        weak_result = match_resume_to_job(weak["resume"], weak["job_description"])

        self.assertGreater(strong_result["match_score"], medium_result["match_score"])
        self.assertGreater(medium_result["match_score"], weak_result["match_score"])
        self.assertEqual(sum(strong_result["score_breakdown"].values()), strong_result["match_score"])

    def test_missing_required_skills_are_prioritized_in_feedback(self):
        fixture = load_fixture("missing_required_skills")
        result = match_resume_to_job(fixture["resume"], fixture["job_description"])

        self.assertIn("AWS", result["missing_skills"])
        self.assertIn("AWS", result["requirements"]["required"])
        self.assertIn("Figma", result["requirements"]["preferred"])
        self.assertTrue(result["recommendations"][0].startswith("Prioritize the required skill AWS"))
        self.assertLess(result["score_breakdown"]["skills"], 45)

    def test_seniority_mismatch_is_documented_without_assumption(self):
        fixture = load_fixture("seniority_mismatch")
        result = match_resume_to_job(fixture["resume"], fixture["job_description"])

        self.assertEqual(result["score_breakdown"]["seniority"], 0)
        self.assertTrue(any("required senior-level role" in gap for gap in result["gaps"]))
        self.assertTrue(any("documented seniority" in item for item in result["recommendations"]))

    def test_explicit_experience_requirement_requires_completed_dated_evidence(self):
        fixture = load_fixture("experience_mismatch")
        result = match_resume_to_job(fixture["resume"], fixture["job_description"])

        self.assertEqual(result["score_breakdown"]["experience"], 0)
        self.assertTrue(any("3+ years of Shopify" in gap for gap in result["gaps"]))
        self.assertTrue(any("accurate dates" in item for item in result["recommendations"]))

    def test_keyword_coverage_is_repeatable_and_reports_missing_terms(self):
        fixture = load_fixture("missing_required_skills")
        first_result = match_resume_to_job(fixture["resume"], fixture["job_description"])
        second_result = match_resume_to_job(fixture["resume"], fixture["job_description"])

        self.assertEqual(first_result["keyword_coverage"], second_result["keyword_coverage"])
        self.assertIn("skill:AWS", first_result["keyword_coverage"]["missing_keywords"])
        self.assertEqual(
            first_result["keyword_coverage"]["percentage"],
            round(100 * first_result["keyword_coverage"]["matched"] / first_result["keyword_coverage"]["total"]),
        )


if __name__ == "__main__":
    unittest.main()
