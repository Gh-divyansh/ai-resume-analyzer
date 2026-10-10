import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.bullet_improver import (
    BulletImprovementGenerationError,
    improve_resume_bullet,
)


RESUME = {
    "name": "Test Candidate",
    "title": "React Developer",
    "summary": "Frontend developer with documented React and API integration experience.",
    "skills": ["React", "Node.js", "REST APIs"],
    "experience": [
        {
            "company": "Example Labs",
            "role": "React Developer",
            "duration": "2021 - 2024",
            "responsibilities": ["Built React interfaces that integrated with Node.js REST APIs."],
        }
    ],
    "education": [],
    "projects": [],
}
JOB_DESCRIPTION = "React Developer. React, Node.js, and REST APIs are required. Build web interfaces."
BULLET = "Built React interfaces that integrated with Node.js REST APIs."


def gemini_response(improved: str, **extra: object) -> SimpleNamespace:
    return SimpleNamespace(parsed={"improved": improved, **extra}, text=None)


class BulletImproverTests(unittest.TestCase):
    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_valid_documented_bullet_returns_typed_safe_response(self, generate_content):
        generate_content.return_value = gemini_response(
            "Developed React interfaces that integrated with Node.js REST APIs."
        )

        result = improve_resume_bullet(
            RESUME,
            JOB_DESCRIPTION,
            BULLET,
            context={"company": "Example Labs", "role": "React Developer", "section": "experience"},
        )

        self.assertEqual(result["original"], BULLET)
        self.assertEqual(result["improved"], "Developed React interfaces that integrated with Node.js REST APIs.")
        self.assertEqual(result["facts_used"], [BULLET])
        self.assertEqual(result["keywords_added"], [])
        self.assertIn("without adding facts", result["reason"])
        generate_content.assert_called_once()

    def test_unsupported_bullet_is_rejected_before_gemini_is_called(self):
        with patch("app.services.bullet_improver.client.models.generate_content") as generate_content:
            with self.assertRaisesRegex(ValueError, "must exactly match"):
                improve_resume_bullet(RESUME, JOB_DESCRIPTION, "Led an AWS migration that cut costs by 40%.")
            generate_content.assert_not_called()

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_generated_metric_is_rejected(self, generate_content):
        generate_content.return_value = gemini_response(
            "Built React interfaces that integrated with Node.js REST APIs and improved performance by 40%."
        )

        with self.assertRaisesRegex(BulletImprovementGenerationError, "unsupported numeric claim"):
            improve_resume_bullet(RESUME, JOB_DESCRIPTION, BULLET)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_new_responsibility_and_omitted_facts_are_rejected(self, generate_content):
        generate_content.return_value = gemini_response("Optimized application performance.")

        with self.assertRaisesRegex(BulletImprovementGenerationError, "protected factual claims"):
            improve_resume_bullet(RESUME, JOB_DESCRIPTION, BULLET)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_safe_cross_domain_action_paraphrases_preserve_facts(self, generate_content):
        samples = [
            ("Teacher", "Developed lesson plans and assessed student progress.", "Created lesson plans and evaluated student progress."),
            ("Chef", "Managed kitchen operations and prepared daily menus.", "Oversaw kitchen operations and prepared daily menus."),
            ("Registered Nurse", "Administered medications and monitored patient recovery.", "Provided medications and assessed patient recovery."),
            ("Accountant", "Prepared monthly financial reports and reconciled accounts.", "Compiled monthly financial reports and reconciled accounts."),
            ("Sales Manager", "Managed client relationships and exceeded quarterly targets.", "Oversaw client relationships and exceeded quarterly targets."),
        ]

        for role, bullet, improved in samples:
            resume = {
                **RESUME,
                "title": role,
                "experience": [{**RESUME["experience"][0], "role": role, "responsibilities": [bullet]}],
            }
            generate_content.return_value = gemini_response(improved)

            result = improve_resume_bullet(resume, f"{role} role", bullet)

            self.assertEqual(result["improved"], improved)
            self.assertEqual(result["facts_used"], [bullet])

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_bounded_action_paraphrases_do_not_create_new_responsibilities(self, generate_content):
        samples = [
            ("Developed Shopify themes using Liquid.", "Created Shopify themes using Liquid."),
            ("Developed web applications.", "Built web applications."),
            ("Analyzed customer data.", "Evaluated customer data."),
            ("Maintained client systems.", "Supported client systems."),
        ]

        for bullet, improved in samples:
            resume = {
                **RESUME,
                "experience": [{**RESUME["experience"][0], "responsibilities": [bullet]}],
            }
            generate_content.return_value = gemini_response(improved)

            result = improve_resume_bullet(resume, "Relevant role", bullet)

            self.assertEqual(result["improved"], improved)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_material_responsibility_expansion_is_rejected_despite_action_paraphrases(self, generate_content):
        source_bullet = "Developed Shopify themes."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }

        for improved in (
            "Led Shopify theme development.",
            "Managed a team developing Shopify themes.",
            "Architected enterprise Shopify infrastructure.",
        ):
            generate_content.return_value = gemini_response(improved)
            with self.assertRaises(BulletImprovementGenerationError):
                improve_resume_bullet(resume, "Shopify Developer role", source_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_award_verb_can_be_paraphrased_when_named_achievement_is_preserved(self, generate_content):
        source_bullet = "Awarded Third Prize at a Science Project Exhibition."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }
        generate_content.return_value = gemini_response(
            "Won Third Prize at the Science Project Exhibition."
        )

        result = improve_resume_bullet(resume, "Science educator role", source_bullet)

        self.assertEqual(result["improved"], "Won Third Prize at the Science Project Exhibition.")
        self.assertEqual(result["facts_used"], [source_bullet])

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_achievement_level_and_numbers_remain_protected(self, generate_content):
        source_bullet = "Awarded Third Prize at a Science Project Exhibition in 2023 after 5 years of study."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }

        generate_content.return_value = gemini_response(
            "Won First Prize at the Science Project Exhibition in 2023 after 5 years of study."
        )
        with self.assertRaisesRegex(BulletImprovementGenerationError, "omitted protected.*third"):
            improve_resume_bullet(resume, "Science educator role", source_bullet)

        generate_content.return_value = gemini_response(
            "Won Third Prize at the Science Project Exhibition in 2024 after 8 years of study."
        )
        with self.assertRaisesRegex(BulletImprovementGenerationError, "numeric claim"):
            improve_resume_bullet(resume, "Science educator role", source_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_new_responsibility_and_credential_claims_remain_rejected(self, generate_content):
        source_bullet = "Awarded Third Prize at a Science Project Exhibition."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }

        generate_content.return_value = gemini_response(
            "Managed the Science Project Exhibition and won Third Prize."
        )
        with self.assertRaisesRegex(BulletImprovementGenerationError, "unsupported factual claims"):
            improve_resume_bullet(resume, "Science educator role", source_bullet)

        generate_content.return_value = gemini_response(
            "Won Third Prize at the Science Project Exhibition as a Certified Educator."
        )
        with self.assertRaisesRegex(BulletImprovementGenerationError, "unsupported factual.*certified"):
            improve_resume_bullet(resume, "Science educator role", source_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_project_award_wording_is_validated_by_factual_claims_not_actions(self, generate_content):
        source_bullet = "Intelligent Restaurant Service & Billing System - awarded Third Prize at a Science Project Exhibition."
        improved_bullet = "Developed an Intelligent Restaurant Service & Billing System, earning Third Prize at a Science Project Exhibition."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }
        generate_content.return_value = gemini_response(improved_bullet)

        result = improve_resume_bullet(resume, "Restaurant systems role", source_bullet)

        self.assertEqual(result["improved"], improved_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_title_case_domain_concepts_do_not_block_safe_shopify_rewrites(self, generate_content):
        samples = [
            (
                "Custom Shopify Theme Development with OS 2.0 Section/Block Architecture.",
                "Leveraging Shopify's Online Store 2.0 section/block architecture.",
            ),
            (
                "Shopify Third-Party API Integration (Payment, Shipping, CRM).",
                "Integrated Shopify third-party APIs for payment gateways, shipping providers, and CRM systems.",
            ),
        ]

        for source_bullet, improved_bullet in samples:
            resume = {
                **RESUME,
                "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
            }
            generate_content.return_value = gemini_response(improved_bullet)

            result = improve_resume_bullet(resume, "Shopify Developer role", source_bullet)

            self.assertEqual(result["improved"], improved_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_claim_comparison_rejects_unrelated_material_object(self, generate_content):
        source_bullet = "Developed Shopify themes."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }
        generate_content.return_value = gemini_response("Developed Shopify landing pages.")

        with self.assertRaisesRegex(BulletImprovementGenerationError, "material factual content"):
            improve_resume_bullet(resume, "Shopify Developer role", source_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_one_gemini_repair_can_replace_residual_wording_only_content(self, generate_content):
        source_bullet = "Analyzed customer feedback."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }
        generate_content.side_effect = [
            gemini_response("Evaluated customer feedback insights."),
            gemini_response("Reviewed customer feedback."),
        ]

        result = improve_resume_bullet(resume, "Customer service role", source_bullet)

        self.assertEqual(result["improved"], "Reviewed customer feedback.")
        self.assertEqual(generate_content.call_count, 2)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_regular_verb_form_is_not_treated_as_material_content(self, generate_content):
        source_bullet = "Custom Shopify Theme Development with OS 2.0 Section/Block Architecture."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }
        generate_content.return_value = gemini_response(
            "Utilizing Shopify's Online Store 2.0 section/block architecture."
        )

        result = improve_resume_bullet(resume, "Shopify Developer role", source_bullet)

        self.assertEqual(result["improved"], "Utilizing Shopify's Online Store 2.0 section/block architecture.")
        generate_content.assert_called_once()

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_factual_rejection_logs_claim_level_root_cause(self, generate_content):
        source_bullet = "Custom Shopify theme development implementing OS 2.0 section/block architecture."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }
        generate_content.return_value = gemini_response(
            "Developed Shopify themes using Magento 2.0 architecture."
        )

        with self.assertLogs("app.services.bullet_improver", level="WARNING") as logs:
            with self.assertRaises(BulletImprovementGenerationError):
                improve_resume_bullet(resume, "Shopify Developer role", source_bullet)

        self.assertIn("source_claims=", "\n".join(logs.output))
        self.assertIn("missing=", "\n".join(logs.output))

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_claim_validator_rejects_cross_domain_material_expansion(self, generate_content):
        cases = [
            ("Worked as a teacher.", "Managed a department of 20 teachers."),
            ("Handled customer accounts.", "Managed $2M in customer accounts."),
            ("Provided patient care.", "Provided patient care as a Registered Nurse."),
        ]

        for source_bullet, improved_bullet in cases:
            resume = {
                **RESUME,
                "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
            }
            generate_content.return_value = gemini_response(improved_bullet)

            with self.assertRaises(BulletImprovementGenerationError):
                improve_resume_bullet(resume, "Relevant role", source_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_shopify_contextual_terms_can_be_omitted_without_losing_hard_facts(self, generate_content):
        source_bullet = "Custom Shopify theme development implementing OS 2.0 section/block architecture."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }

        for improved in (
            "Developed Shopify themes using OS 2.0 architecture.",
            "Built Shopify themes using OS 2.0.",
        ):
            generate_content.return_value = gemini_response(improved)
            result = improve_resume_bullet(resume, "Shopify Developer role", source_bullet)
            self.assertEqual(result["improved"], improved)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_shopify_technology_and_version_facts_remain_protected(self, generate_content):
        source_bullet = "Custom Shopify theme development implementing OS 2.0 section/block architecture."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }

        generate_content.return_value = gemini_response(
            "Developed WordPress themes using OS 2.0 architecture."
        )
        with self.assertRaisesRegex(BulletImprovementGenerationError, "(?i)protected factual claims.*shopify"):
            improve_resume_bullet(resume, "Shopify Developer role", source_bullet)

        generate_content.return_value = gemini_response(
            "Developed Shopify themes using Magento 2.0 architecture."
        )
        with self.assertRaisesRegex(BulletImprovementGenerationError, "(?i)protected factual.*version:os 2\\.0"):
            improve_resume_bullet(resume, "Shopify Developer role", source_bullet)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_new_technology_claim_is_rejected_and_keywords_are_derived_safely(self, generate_content):
        generate_content.return_value = gemini_response(
            "Built React interfaces with AWS that integrated with Node.js REST APIs.",
            keywords_added=["AWS"],
        )

        with self.assertRaisesRegex(BulletImprovementGenerationError, "technology not present"):
            improve_resume_bullet(RESUME, "React and AWS are required.", BULLET)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_supported_keyword_normalization_is_reported(self, generate_content):
        source_bullet = "Built React interfaces that integrated with a REST API."
        resume = {
            **RESUME,
            "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
        }
        generate_content.return_value = gemini_response(
            "Developed React interfaces that integrated with REST APIs."
        )

        result = improve_resume_bullet(
            resume,
            "React and REST APIs are required for this role.",
            source_bullet,
        )

        self.assertEqual(result["keywords_added"], ["REST APIs"])
        self.assertEqual(result["facts_used"], [source_bullet])

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_response_handling_is_repeatable_and_ignores_model_claim_lists(self, generate_content):
        generate_content.return_value = gemini_response(
            "Developed React interfaces that integrated with Node.js REST APIs.",
            facts_used=["Invented achievement"],
            keywords_added=["AWS"],
        )

        first = improve_resume_bullet(RESUME, JOB_DESCRIPTION, BULLET)
        second = improve_resume_bullet(RESUME, JOB_DESCRIPTION, BULLET)

        self.assertEqual(first, second)
        self.assertEqual(first["facts_used"], [BULLET])
        self.assertEqual(first["keywords_added"], [])

    def test_endpoint_returns_400_for_missing_or_unsupported_input(self):
        client = TestClient(app)
        missing_resume = client.post("/api/resume/improve-bullet", json={"job_description": JOB_DESCRIPTION, "bullet": BULLET})
        blank_job_description = client.post("/api/resume/improve-bullet", json={"resume": RESUME, "job_description": " ", "bullet": BULLET})
        missing_bullet = client.post("/api/resume/improve-bullet", json={"resume": RESUME, "job_description": JOB_DESCRIPTION})
        unsupported_bullet = client.post(
            "/api/resume/improve-bullet",
            json={"resume": RESUME, "job_description": JOB_DESCRIPTION, "bullet": "Invented responsibility."},
        )

        self.assertEqual(missing_resume.status_code, 400)
        self.assertEqual(blank_job_description.status_code, 400)
        self.assertEqual(missing_bullet.status_code, 400)
        self.assertEqual(unsupported_bullet.status_code, 400)

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_endpoint_returns_valid_improvement_schema(self, generate_content):
        generate_content.return_value = gemini_response(
            "Developed React interfaces that integrated with Node.js REST APIs."
        )

        response = TestClient(app).post(
            "/api/resume/improve-bullet",
            json={"resume": RESUME, "job_description": JOB_DESCRIPTION, "bullet": BULLET},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {"original", "improved", "reason", "keywords_added", "facts_used"},
        )

    @patch("app.services.bullet_improver.client.models.generate_content")
    def test_endpoint_returns_200_for_three_dashboard_project_rewrites(self, generate_content):
        cases = [
            (
                "Custom Shopify Theme Development with OS 2.0 Section/Block Architecture.",
                "Developed Shopify themes using OS 2.0 section/block architecture.",
            ),
            (
                "Shopify Third-Party API Integration (Payment, Shipping, CRM).",
                "Integrated Shopify third-party APIs for payment, shipping, and CRM.",
            ),
            (
                "Intelligent Restaurant Service & Billing System - awarded Third Prize at a Science Project Exhibition.",
                "Developed an Intelligent Restaurant Service & Billing System, earning Third Prize at a Science Project Exhibition.",
            ),
        ]
        client = TestClient(app)

        for source_bullet, improved_bullet in cases:
            resume = {
                **RESUME,
                "experience": [{**RESUME["experience"][0], "responsibilities": [source_bullet]}],
            }
            generate_content.return_value = gemini_response(improved_bullet)

            response = client.post(
                "/api/resume/improve-bullet",
                json={"resume": resume, "job_description": "Relevant role", "bullet": source_bullet},
            )

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["improved"], improved_bullet)


if __name__ == "__main__":
    unittest.main()
