import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.schemas.universal_match import UniversalAIAnalysis
from app.services.universal_ai_matcher import (
    UniversalAIGenerationError,
    extract_universal_ai_analysis,
    match_resume_to_job_universal,
    score_universal_analysis,
)


def analysis(requirements):
    return UniversalAIAnalysis.model_validate({"requirements": requirements, "overall_explanation": "Source-grounded review."})


class UniversalAIMatcherTests(unittest.TestCase):
    @staticmethod
    def _response(payload):
        return type("Response", (), {"parsed": payload, "text": ""})()

    @staticmethod
    def _payload():
        return {"requirements":[{"id":"python","label":"Python","category":"skill","priority":"required","minimum_years":None,"evidence":[],"explanation":"Required."},{"id":"aws","label":"AWS","category":"skill","priority":"preferred","minimum_years":None,"evidence":[],"explanation":"Preferred."}],"overall_explanation":"Complete review."}

    def test_transient_generation_error_retries_with_backoff(self):
        transient = RuntimeError("429 rate limit")
        with patch("app.services.universal_ai_matcher.client.models.generate_content", side_effect=[transient, self._response(self._payload())]) as generate, patch("app.services.universal_ai_matcher.time.sleep") as sleep:
            parsed, metadata = extract_universal_ai_analysis({"skills": []}, "Python required.", include_metadata=True)
        self.assertEqual(parsed.requirements[0].label, "Python")
        self.assertEqual(metadata.retries, 1)
        self.assertEqual(generate.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_permanent_generation_error_does_not_retry(self):
        with patch("app.services.universal_ai_matcher.client.models.generate_content", side_effect=RuntimeError("invalid API key")) as generate, patch("app.services.universal_ai_matcher.time.sleep") as sleep:
            with self.assertRaises(UniversalAIGenerationError) as caught:
                extract_universal_ai_analysis({"skills": []}, "Python required.")
        self.assertFalse(caught.exception.transient)
        self.assertEqual(caught.exception.attempts, 1)
        self.assertEqual(generate.call_count, 1)
        sleep.assert_not_called()

    def test_malformed_structured_output_gets_one_or_more_format_correction_attempts(self):
        malformed = type("Response", (), {"parsed": {"requirements": [], "overall_explanation": "Incomplete."}, "text": ""})()
        with patch("app.services.universal_ai_matcher.client.models.generate_content", side_effect=[malformed, self._response(self._payload())]) as generate, patch("app.services.universal_ai_matcher.time.sleep") as sleep:
            parsed, metadata = extract_universal_ai_analysis({"skills": []}, "Python required.", include_metadata=True)
        self.assertEqual(parsed.requirements[0].label, "Python")
        self.assertEqual(metadata.retries, 1)
        self.assertEqual(generate.call_count, 2)
        self.assertIn("previous response was invalid or incomplete", generate.call_args.kwargs["contents"])
        sleep.assert_not_called()

    def test_repeated_malformed_structured_output_is_a_format_failure(self):
        malformed = type("Response", (), {"parsed": {"requirements": [], "overall_explanation": "Incomplete."}, "text": ""})()
        with patch("app.services.universal_ai_matcher.client.models.generate_content", return_value=malformed) as generate:
            with self.assertRaises(UniversalAIGenerationError) as caught:
                extract_universal_ai_analysis({"skills": []}, "Python required.")
        self.assertEqual(caught.exception.kind, "format")
        self.assertFalse(caught.exception.transient)
        self.assertEqual(caught.exception.attempts, 3)
        self.assertEqual(generate.call_count, 3)

    def test_prompt_requires_complete_priority_aware_cross_domain_extraction(self):
        with patch("app.services.universal_ai_matcher.client.models.generate_content", return_value=self._response(self._payload())) as generate:
            result = extract_universal_ai_analysis({"skills": []}, "Python required. AWS preferred.")
        prompt = generate.call_args.kwargs["contents"]
        self.assertEqual([item.priority.value for item in result.requirements], ["required", "preferred"])
        self.assertIn("COMPLETE structured resume", prompt)
        self.assertIn("every meaningful JD requirement", prompt)
        self.assertIn("role/title (use category `domain_knowledge`)", prompt)
        self.assertIn("never use combined labels such as `role|title`", prompt)
        self.assertIn("Semantic equivalents", prompt)
        self.assertIn("explicit seniority level", prompt)
        self.assertIn("Skills section is `explicit` evidence", prompt)
        config = generate.call_args.kwargs["config"]
        self.assertEqual(config.seed, 0)
        self.assertIsNone(config.response_schema)
    def test_cross_domain_semantic_evidence_cases_are_deterministic(self):
        cases = json.loads((Path(__file__).parent / "fixtures" / "universal_ai_cross_domain.json").read_text())
        self.assertEqual(len(cases), 11)
        for case in cases:
            resume = {"title": case["title"], "skills": [], "summary": "", "experience": [{"role": case["title"], "duration": "2019 - 2024", "responsibilities": [case["quote"]]}], "education": [], "projects": []}
            ai = analysis([{"id": "evidence", "label": case["label"], "category": case["category"], "priority": "required", "minimum_years": None, "evidence": [{"source_section": "experience", "quote": case["quote"], "strength": "experience", "explanation": "Semantic evidence is documented in experience."}], "explanation": "Matched from the documented bullet."}])
            with patch("app.services.universal_ai_matcher.extract_universal_ai_analysis", return_value=ai):
                first = match_resume_to_job_universal(resume, case["jd"])
                second = match_resume_to_job_universal(resume, case["jd"])
            with self.subTest(domain=case["domain"]):
                self.assertEqual(first, second)
                self.assertGreater(first["match_score"], 0)
                self.assertEqual(first["matcher"], "universal_ai")

    def test_keyword_only_and_ungrounded_evidence_do_not_match(self):
        resume = {"title": "Candidate", "summary": "Familiar with BLS terminology.", "skills": [], "experience": [], "education": [], "projects": []}
        ai = analysis([{"id":"bls","label":"BLS certification","category":"credential","priority":"required","minimum_years":None,"evidence":[{"source_section":"summary","quote":"BLS terminology","strength":"keyword_only","explanation":"A summary mention is not a credential."}],"explanation":"No explicit credential is documented."}])
        with patch("app.services.universal_ai_matcher.extract_universal_ai_analysis", return_value=ai):
            result = match_resume_to_job_universal(resume, "BLS certification required.")
        self.assertEqual(result["match_score"], 0)
        self.assertEqual(result["missing_skills"], ["BLS certification"])

    def test_invented_resume_facts_cannot_become_supported_evidence(self):
        """Exact citation grounding blocks fabricated facts in every source section."""
        resume = {
            "title": "Assistant",
            "summary": "Organized records.",
            "skills": ["Spreadsheets"],
            "experience": [{"role": "Assistant", "duration": "2023 - 2024", "responsibilities": ["Organized records."]}],
            "education": [{"degree": "Diploma", "institution": "College", "duration": "2022"}],
            "projects": [],
        }
        fabricated_facts = [
            "AWS", "Registered Nurse", "MBA", "2010 - 2020", "Acme Corporation",
            "Managed a team", "Employee of the Year", "increased sales by 40%", "Senior Director",
        ]
        ai = analysis([
            {
                "id": f"invented-{index}", "label": fact, "category": "competency",
                "priority": "required", "minimum_years": None,
                "evidence": [{"source_section": "experience", "quote": fact, "strength": "experience", "explanation": "Claimed evidence."}],
                "explanation": "Claimed requirement match.",
            }
            for index, fact in enumerate(fabricated_facts)
        ])
        scored = score_universal_analysis(resume, ai)
        self.assertEqual(scored["matched"], [])
        self.assertEqual({item.label for item in scored["missing"]}, set(fabricated_facts))

    def test_required_preferred_experience_and_seniority_are_scored_locally(self):
        resume = {"title":"Senior Analyst", "summary":"", "skills":["SQL"], "experience":[{"role":"Senior Analyst","duration":"2019 - 2024","responsibilities":["Analyzed customer data."]}], "education":[], "projects":[]}
        ai = analysis([
            {"id":"sql","label":"SQL","category":"skill","priority":"required","minimum_years":None,"evidence":[{"source_section":"skills","quote":"SQL","strength":"explicit","explanation":"Listed skill."}],"explanation":"Matched."},
            {"id":"excel","label":"Excel","category":"skill","priority":"preferred","minimum_years":None,"evidence":[],"explanation":"Not documented."},
            {"id":"years","label":"Analytics experience","category":"experience","priority":"required","minimum_years":3,"evidence":[{"source_section":"experience","quote":"Analyzed customer data.","strength":"experience","explanation":"Experience bullet."}],"explanation":"Dated evidence."},
            {"id":"senior","label":"Senior level","category":"seniority","priority":"required","minimum_years":None,"evidence":[{"source_section":"experience","quote":"Senior Analyst","strength":"experience","explanation":"Documented role."}],"explanation":"Title evidence."}
        ])
        first, second = score_universal_analysis(resume, ai), score_universal_analysis(resume, ai)
        self.assertEqual(first, second)
        self.assertGreater(first["score_breakdown"]["skills"], 30)
        self.assertEqual(first["score_breakdown"]["experience"], 20)
        self.assertEqual(first["score_breakdown"]["seniority"], 10)

    def test_education_only_skill_and_insufficient_years_do_not_satisfy_requirements(self):
        resume = {"title":"Candidate", "summary":"", "skills":[], "experience":[{"role":"Assistant","duration":"2023 - 2024","responsibilities":["Supported records."]}], "education":[{"degree":"Coursework in customer relationships", "institution":"Example", "duration":"2022"}], "projects":[]}
        ai = analysis([
            {"id":"relationships","label":"Customer relationships","category":"competency","priority":"required","minimum_years":None,"evidence":[{"source_section":"education","quote":"customer relationships","strength":"education","explanation":"Coursework mention only."}],"explanation":"Not practical evidence."},
            {"id":"years","label":"Administration experience","category":"experience","priority":"required","minimum_years":3,"evidence":[{"source_section":"experience","quote":"Supported records.","strength":"experience","explanation":"Only one documented year."}],"explanation":"Insufficient duration."}
        ])
        scored = score_universal_analysis(resume, ai)
        self.assertEqual({item.id for item in scored["missing"]}, {"relationships", "years"})

    def test_documented_experience_duration_is_a_grounded_citation(self):
        resume = {"title":"Analyst", "summary":"", "skills":[], "experience":[{"role":"Analyst", "duration":"2019 - 2024", "responsibilities":["Analyzed records."]}], "education":[], "projects":[]}
        ai = analysis([{"id":"years","label":"Analytics experience","category":"experience","priority":"required","minimum_years":3,"evidence":[{"source_section":"experience","quote":"2019 - 2024","strength":"experience","explanation":"Documented duration."}],"explanation":"Dated experience."}])
        scored = score_universal_analysis(resume, ai)
        self.assertEqual([item.id for item in scored["matched"]], ["years"])


if __name__ == "__main__":
    unittest.main()
