import unittest

from tests.run_domain_evaluation import run_evaluation


class DomainEvaluationRunnerTests(unittest.TestCase):
    def test_fixed_cross_domain_matrix_is_deterministic_and_complete(self):
        first = run_evaluation()
        second = run_evaluation()
        self.assertEqual(first, second)
        self.assertEqual(first["case_count"], 156)
        self.assertEqual(first["overall"]["correct"], 156)
        self.assertEqual(first["overall"].get("incorrect", 0), 0)
        self.assertTrue(all(value["status"] == "YELLOW" for value in first["domains"].values()))


if __name__ == "__main__":
    unittest.main()
