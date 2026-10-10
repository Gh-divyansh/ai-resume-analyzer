import copy
import unittest

from app.services.competency_packs import NONTECHNICAL_PACK_STATUS, PackStatus
from app.services.domain_pack_evaluator import evaluate_domain_pack_projection
from app.services.active_domain_matcher import apply_active_domain_packs
from app.services.job_matcher import match_resume_to_job


HEALTHCARE_RESUME = {
    "title": "Registered Nurse",
    "summary": "Interested in healthcare terminology.",
    "skills": ["BLS certification"],
    "experience": [{"role": "Registered Nurse", "duration": "2020 - 2024", "responsibilities": ["Provided acute care and completed clinical documentation."]}],
    "education": [], "projects": [],
}


class ActiveDomainMatcherTests(unittest.TestCase):
    def test_only_healthcare_is_active(self):
        self.assertEqual(NONTECHNICAL_PACK_STATUS["healthcare-core"], PackStatus.active)
        self.assertTrue(all(status is not PackStatus.active for pack, status in NONTECHNICAL_PACK_STATUS.items() if pack != "healthcare-core"))

    def test_healthcare_requirements_are_additive_in_production_response(self):
        result = match_resume_to_job(HEALTHCARE_RESUME, "Registered Nurse with 3+ years acute care experience and BLS certification required.")
        self.assertIn("Patient care", result["matched_skills"])
        self.assertIn("BLS certification", result["matched_skills"])
        self.assertIn("Patient care", result["requirements"]["required"])
        self.assertGreater(result["match_score"], 0)
        self.assertEqual(result["title_alignment"], 10)

    def test_mixed_healthcare_and_technology_jd_includes_both_evidence_sets(self):
        resume = copy.deepcopy(HEALTHCARE_RESUME)
        resume["skills"].append("Python")
        result = match_resume_to_job(resume, "Registered Nurse with BLS certification and Python required.")
        self.assertIn("Python", result["matched_skills"])
        self.assertIn("BLS certification", result["matched_skills"])

    def test_missing_credential_duration_and_seniority_remain_visible(self):
        resume = {**HEALTHCARE_RESUME, "title": "Nurse", "skills": [], "experience": [{"role": "Nurse", "duration": "2023 - 2024", "responsibilities": ["Provided acute care and led daily handovers."]}]}
        result = match_resume_to_job(resume, "Senior Registered Nurse with 3+ years acute care experience and BLS certification required.")
        self.assertIn("BLS certification", result["missing_skills"])
        self.assertTrue(any("3+ years of Patient care" in gap for gap in result["gaps"]))
        self.assertTrue(any("senior-level" in gap.lower() for gap in result["gaps"]))

    def test_keyword_only_healthcare_text_is_not_evidence(self):
        resume = {"title": "Candidate", "summary": "Familiar with BLS certification terminology and acute care.", "skills": [], "experience": [], "education": [], "projects": []}
        result = match_resume_to_job(resume, "BLS certification and acute care required.")
        self.assertIn("BLS certification", result["missing_skills"])
        self.assertIn("Patient care", result["missing_skills"])

    def test_inactive_pack_does_not_affect_production_but_is_visible_offline(self):
        resume = {"title": "Teacher", "skills": ["teaching license"], "experience": [{"role": "Teacher", "duration": "2020 - 2024", "responsibilities": ["lesson planning"]}], "education": [], "projects": []}
        jd = "Lesson planning and teaching license required."
        production = match_resume_to_job(resume, jd)
        offline = evaluate_domain_pack_projection(resume, jd)
        self.assertEqual(production["match_score"], 0)
        self.assertGreater(offline["score"], 0)

    def test_technical_only_result_is_a_compatibility_no_op(self):
        resume = {"title": "Python Developer", "skills": ["Python"], "experience": [], "education": [], "projects": []}
        jd = "Python required."
        result = match_resume_to_job(resume, jd)
        self.assertEqual(apply_active_domain_packs(copy.deepcopy(result), resume, jd), result)


if __name__ == "__main__":
    unittest.main()
