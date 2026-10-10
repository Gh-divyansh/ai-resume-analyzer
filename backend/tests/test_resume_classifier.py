"""Offline safety tests for universal resume/CV eligibility classification."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.resume_classifier import ResumeClassificationError, classify_resume_document


class ResumeClassifierTests(unittest.TestCase):
    def test_accepts_only_bounded_classifier_labels(self):
        with patch("app.services.resume_classifier.client.models.generate_content", return_value=SimpleNamespace(parsed={"classification": "resume"})):
            self.assertEqual(classify_resume_document("Professional experience and education"), "resume")
        with patch("app.services.resume_classifier.client.models.generate_content", return_value=SimpleNamespace(parsed={"classification": "not_resume"})):
            self.assertEqual(classify_resume_document("Invoice total"), "not_resume")
        with patch("app.services.resume_classifier.client.models.generate_content", return_value=SimpleNamespace(parsed={"classification": "uncertain"})):
            self.assertEqual(classify_resume_document("garbled text"), "uncertain")

    def test_invalid_or_failed_model_response_fails_closed(self):
        with patch("app.services.resume_classifier.client.models.generate_content", return_value=SimpleNamespace(parsed={"classification": "maybe"})):
            with self.assertRaises(ResumeClassificationError):
                classify_resume_document("Unknown document")
        with patch("app.services.resume_classifier.client.models.generate_content", side_effect=RuntimeError("service unavailable")):
            with self.assertRaises(ResumeClassificationError):
                classify_resume_document("Candidate CV")

    def test_prompt_is_domain_neutral_and_score_independent(self):
        with patch("app.services.resume_classifier.client.models.generate_content", return_value=SimpleNamespace(parsed={"classification": "resume"})) as generate:
            classify_resume_document("International professional curriculum vitae")
        prompt = generate.call_args.kwargs["contents"]
        self.assertIn("worldwide professions", prompt)
        self.assertIn("must not score", prompt)
        self.assertNotIn("software engineer required", prompt)


if __name__ == "__main__":
    unittest.main()
