import unittest

from tests.run_universal_ai_evaluation import run_evaluation
from tests.run_universal_ai_live_validation import _variance_dimensions


class UniversalAIEvaluationRunnerTests(unittest.TestCase):
    def test_offline_evaluation_reports_grounded_repeatable_results(self):
        first, second = run_evaluation(), run_evaluation()
        self.assertEqual(first, second)
        self.assertEqual(first["total_cases"], 16)
        self.assertEqual(first["passed"], 16)
        self.assertEqual(first["failed"], 0)
        self.assertEqual(first["validation_errors"], 0)
        self.assertEqual(first["repeated_call_differences"], [])

    def test_live_variance_dimensions_ignore_explanation_only_changes(self):
        base = {"ai_requirements": [{"label": "Python", "category": "skill", "priority": "required", "minimum_years": None, "evidence": [{"source_section": "skills", "quote": "Python", "strength": "explicit"}]}]}
        explanation_only = {**base, "ai_overall_explanation": "Different prose."}
        changed_evidence = {"ai_requirements": [{"label": "Python", "category": "skill", "priority": "required", "minimum_years": None, "evidence": [{"source_section": "experience", "quote": "Built APIs", "strength": "experience"}]}]}
        self.assertEqual(_variance_dimensions([base, explanation_only]), {"requirements": False, "priorities": False, "evidence": False})
        self.assertEqual(_variance_dimensions([base, changed_evidence]), {"requirements": False, "priorities": False, "evidence": True})


if __name__ == "__main__":
    unittest.main()
