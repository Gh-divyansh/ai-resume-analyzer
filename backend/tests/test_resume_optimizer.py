import json
import unittest
from pathlib import Path

from app.services.job_matcher import match_resume_to_job
from app.services.resume_optimizer import generate_resume_optimizations


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


def optimize_fixture(name: str) -> dict:
    fixture = load_fixture(name)
    match = match_resume_to_job(fixture["resume"], fixture["job_description"])
    return generate_resume_optimizations(fixture["resume"], fixture["job_description"], match)


class ResumeOptimizerTests(unittest.TestCase):
    def test_required_skill_is_high_priority_and_preferred_skill_is_lower_priority(self):
        result = optimize_fixture("missing_required_skills")["recommendations"]
        required = next(item for item in result if "required skill 'AWS'" in item["issue"])
        preferred = next(item for item in result if "preferred skill 'Figma'" in item["issue"])

        self.assertEqual(required["priority"], "high")
        self.assertEqual(preferred["priority"], "low")
        self.assertLess(result.index(required), result.index(preferred))

    def test_experience_and_seniority_gaps_are_specific(self):
        experience = optimize_fixture("experience_mismatch")["recommendations"]
        seniority = optimize_fixture("seniority_mismatch")["recommendations"]

        self.assertTrue(any(item["category"] == "experience" and item["priority"] == "high" for item in experience))
        self.assertTrue(any(item["category"] == "seniority" and item["priority"] == "high" for item in seniority))

    def test_keyword_and_responsibility_gaps_are_grounded_in_matcher_output(self):
        fixture = load_fixture("weak_match")
        match = match_resume_to_job(fixture["resume"], fixture["job_description"])
        result = generate_resume_optimizations(fixture["resume"], fixture["job_description"], match)["recommendations"]

        self.assertTrue(any(item["category"] == "keywords" for item in result))
        self.assertTrue(any(item["category"] == "responsibilities" for item in result))
        keyword = next(item for item in result if item["category"] == "keywords")
        responsibility = next(item for item in result if item["category"] == "responsibilities")
        self.assertIn("matcher", keyword["reason"])
        self.assertIn("matcher", responsibility["reason"])

    def test_output_is_deterministic_and_deduplicated(self):
        fixture = load_fixture("missing_required_skills")
        match = match_resume_to_job(fixture["resume"], fixture["job_description"])
        first = generate_resume_optimizations(fixture["resume"], fixture["job_description"], match)
        second = generate_resume_optimizations(fixture["resume"], fixture["job_description"], match)

        self.assertEqual(first, second)
        keys = {(item["category"], item["issue"].casefold()) for item in first["recommendations"]}
        self.assertEqual(len(keys), len(first["recommendations"]))

    def test_recommendations_do_not_claim_undocumented_qualifications(self):
        result = optimize_fixture("missing_required_skills")["recommendations"]
        required = next(item for item in result if "required skill 'AWS'" in item["issue"])
        combined = " ".join(required.values()).casefold()

        self.assertIn("if you have", combined)
        self.assertNotIn("you have hands-on aws experience.", combined)
        self.assertNotIn("amazon", combined)

    def test_match_is_computed_only_when_not_supplied(self):
        fixture = load_fixture("medium_match")
        explicit_match = match_resume_to_job(fixture["resume"], fixture["job_description"])

        self.assertEqual(
            generate_resume_optimizations(fixture["resume"], fixture["job_description"]),
            generate_resume_optimizations(fixture["resume"], fixture["job_description"], explicit_match),
        )

    def test_invalid_optimizer_inputs_return_clear_errors(self):
        with self.assertRaisesRegex(ValueError, "Resume data must be an object"):
            generate_resume_optimizations([], "Python developer")

        with self.assertRaisesRegex(ValueError, "Job description is required"):
            generate_resume_optimizations({}, "   ")

        with self.assertRaisesRegex(ValueError, "Job match result must be an object"):
            generate_resume_optimizations({}, "Python developer", [])


if __name__ == "__main__":
    unittest.main()
