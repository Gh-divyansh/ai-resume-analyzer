import unittest

from tests.run_healthcare_validation import run_validation


class HealthcareValidationRunnerTests(unittest.TestCase):
    def test_realistic_synthetic_healthcare_validation_is_repeatable(self):
        first = run_validation()
        second = run_validation()
        self.assertEqual(first, second)
        self.assertEqual(first["total_cases"], 13)
        self.assertEqual(first["correct"], 13)
        self.assertEqual(first["false_positives"], 0)
        self.assertEqual(first["false_negatives"], 0)
        self.assertEqual(first["failing_cases"], [])


if __name__ == "__main__":
    unittest.main()
