import json
import unittest
from pathlib import Path

from app.services.competency_packs import load_nontechnical_packs
from app.services.domain_pack_evaluator import (
    build_domain_requirement_records,
    evaluate_domain_pack_projection,
    evaluate_domain_pack_side_by_side,
)
from app.services.technology_core_evaluator import evaluate_technology_core_parity


class DomainPackProjectionTests(unittest.TestCase):
    @staticmethod
    def _resume(*, title="Candidate", skills=None, duration="2020 - 2024", responsibilities=None):
        return {
            "title": title,
            "skills": skills or [],
            "experience": [{"role": title, "duration": duration, "responsibilities": responsibilities or []}],
            "education": [],
            "projects": [],
        }
    def test_all_bounded_nontechnical_packs_validate(self):
        packs = load_nontechnical_packs()
        self.assertEqual(len(packs), 12)
        self.assertEqual(len({pack.pack_id for pack in packs}), 12)

    def test_cross_domain_projection_is_deterministic_and_surfaces_gaps(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures" / "domain_pack_calibration.json").read_text(encoding="utf-8"))
        results = {}
        for fixture in fixtures:
            first = evaluate_domain_pack_projection(fixture["resume"], fixture["jd"])
            second = evaluate_domain_pack_projection(fixture["resume"], fixture["jd"])
            self.assertEqual(first["score"], second["score"], fixture["name"])
            self.assertGreaterEqual(first["score"], fixture["minimum"], fixture["name"])
            results[fixture["name"]] = first
        self.assertIn("healthcare.bls", results["missing_credential"]["missing"])
        self.assertIn("healthcare.patient_care", results["missing_experience_duration"]["missing"])
        self.assertIn("seniority.senior", results["seniority_mismatch"]["missing"])
        self.assertEqual(results["weak_unrelated"]["score"], 0)
        self.assertGreater(results["strong_healthcare"]["score"], results["medium_education"]["score"])

    def test_technology_core_parity_remains_exact(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "strong_match.json").read_text(encoding="utf-8"))
        evaluation = evaluate_technology_core_parity(fixture["resume"], fixture["job_description"])
        self.assertTrue(all(evaluation["parity"].values()))

    def test_healthcare_jd_is_separated_into_title_duration_domain_and_credential_evidence(self):
        jd = "Registered Nurse with 3+ years acute-care experience and current BLS certification."
        requirements = build_domain_requirement_records(jd)
        by_id = {record.canonical_id: record for record in requirements}
        self.assertEqual(by_id["healthcare.registered_nurse"].evidence_type.value, "title")
        self.assertEqual(by_id["healthcare.patient_care"].minimum_years, 3)
        self.assertEqual(by_id["healthcare.bls"].category.value, "credential")

    def test_side_by_side_projection_is_explicitly_inactive(self):
        evaluation = evaluate_domain_pack_side_by_side(
            {"title": "Registered Nurse", "skills": ["BLS certification"], "experience": [], "education": [], "projects": []},
            "Registered Nurse with BLS certification required.",
        )
        self.assertFalse(evaluation["active"])
        self.assertIn("match_score", evaluation["legacy"])
        self.assertGreater(evaluation["domain_pack_projection"]["score"], 0)

    def test_seniority_is_title_only_and_a_mismatch_is_visible(self):
        result = evaluate_domain_pack_projection(
            {"title": "Nurse", "skills": [], "experience": [{"role": "Nurse", "duration": "2020 - 2024", "responsibilities": ["Led daily handovers."]}], "education": [], "projects": []},
            "Senior Registered Nurse with patient care required.",
        )
        self.assertIn("seniority.senior", result["missing"])
        # "Led" in a responsibility is deliberately not interpreted as a level.
        self.assertNotIn("seniority.senior", result["matched"])

    def test_every_domain_has_explainable_strong_medium_weak_and_gap_calibrations(self):
        matrix = json.loads((Path(__file__).parent / "fixtures" / "domain_pack_matrix.json").read_text(encoding="utf-8"))
        packs = {pack.pack_id: pack for pack in load_nontechnical_packs()}
        self.assertEqual(len(matrix), 12)

        for entry in matrix:
            pack = packs[entry["pack"]]
            credential = next(concept for concept in pack.concepts if concept.category.value == "credential")
            competency = next(concept for concept in pack.concepts if concept.category.value != "credential")
            other = next((concept for concept in pack.concepts if concept.canonical_id != competency.canonical_id and concept.category.value != "credential"), competency)
            credential_text, competency_text, other_text = credential.aliases[0], competency.aliases[0], other.aliases[0]
            jd = f"{competency_text}, {other_text}, and {credential_text} required."
            strong = evaluate_domain_pack_projection(self._resume(skills=[credential_text], responsibilities=[competency_text, other_text]), jd)
            medium = evaluate_domain_pack_projection(self._resume(responsibilities=[competency_text]), jd)
            weak = evaluate_domain_pack_projection(self._resume(responsibilities=[]), jd)
            unrelated = evaluate_domain_pack_projection(self._resume(responsibilities=["unrelated inventory work"]), jd)
            missing_credential = evaluate_domain_pack_projection(self._resume(responsibilities=[competency_text, other_text]), jd)
            duration_jd = f"3+ years {competency_text} experience required."
            missing_duration = evaluate_domain_pack_projection(self._resume(duration="2023 - 2024", responsibilities=[competency_text]), duration_jd)
            seniority = evaluate_domain_pack_projection(self._resume(responsibilities=[competency_text]), f"Senior {competency_text} required.")

            with self.subTest(domain=entry["domain"]):
                self.assertGreater(strong["score"], medium["score"])
                self.assertGreater(medium["score"], weak["score"])
                self.assertEqual(weak["score"], unrelated["score"])
                self.assertIn(credential.canonical_id, missing_credential["missing"])
                self.assertIn(competency.canonical_id, missing_duration["missing"])
                self.assertIn("seniority.senior", seniority["missing"])

    def test_legacy_and_projection_are_compared_without_activating_a_pack(self):
        comparison = evaluate_domain_pack_side_by_side(
            self._resume(skills=["teaching license"], responsibilities=["lesson planning", "classroom management"]),
            "Lesson planning, classroom management, and teaching license required.",
        )
        self.assertFalse(comparison["active"])
        self.assertEqual(comparison["legacy"]["match_score"], 0)
        self.assertGreater(comparison["domain_pack_projection"]["score"], 0)


if __name__ == "__main__":
    unittest.main()
