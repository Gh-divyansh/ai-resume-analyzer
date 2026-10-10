import json
import unittest
from pathlib import Path

from app.schemas.universal_match import RequirementCategory


class UniversalAILiveFixtureTests(unittest.TestCase):
    def test_live_review_fixture_is_diverse_and_has_human_observations(self):
        cases = json.loads((Path(__file__).parent / "fixtures" / "universal_ai_live_review.json").read_text())
        self.assertEqual(len(cases), 15)
        self.assertEqual(len({case["domain"] for case in cases}), 15)
        for case in cases:
            self.assertTrue(case["expected"]["required"])
            self.assertIn("resume", case)
            self.assertIn("jd", case)


if __name__ == "__main__":
    unittest.main()
