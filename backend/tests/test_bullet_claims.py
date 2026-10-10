import json
import unittest
from pathlib import Path

from app.schemas.bullet_claims import ClaimKind
from app.services.bullet_claims import extract_factual_claims, compare_factual_claims


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bullet_claim_audit.json"


class BulletClaimTests(unittest.TestCase):
    def test_cross_domain_safe_rewrites_preserve_claims(self):
        fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(fixtures), 16)
        expected_domains = {
            "Technology - Shopify", "Technology - software", "Healthcare", "Education", "Finance", "Sales",
            "Human resources", "Design", "Engineering", "Hospitality", "Legal", "Customer service", "Skilled trades",
        }
        self.assertTrue(expected_domains.issubset({fixture["domain"] for fixture in fixtures}))
        for fixture in fixtures:
            comparison = compare_factual_claims(fixture["source"], fixture["generated"])

            self.assertEqual(comparison.missing_claims, [], fixture["domain"])
            self.assertEqual(comparison.introduced_claims, [], fixture["domain"])
            self.assertEqual(comparison.introduced_material_content, [], fixture["domain"])

    def test_claim_comparison_detects_factual_expansion(self):
        comparison = compare_factual_claims(
            "Developed Shopify themes.",
            "Led a team of developers to build Shopify themes.",
        )

        self.assertIn(ClaimKind.material_responsibility, {claim.kind for claim in comparison.introduced_claims})

    def test_claim_comparison_preserves_project_award_and_event(self):
        source = "Intelligent Restaurant Service & Billing System - awarded Third Prize at a Science Project Exhibition."
        generated = "Developed an Intelligent Restaurant Service & Billing System, earning Third Prize at a Science Project Exhibition."

        comparison = compare_factual_claims(source, generated)

        self.assertEqual(comparison.missing_claims, [])
        self.assertEqual(comparison.introduced_claims, [])
        self.assertEqual(comparison.introduced_material_content, [])

    def test_title_case_domain_concepts_are_not_named_entities(self):
        claims = extract_factual_claims("Custom Shopify Theme Development with OS 2.0 Section/Block Architecture.")

        self.assertIn((ClaimKind.technology, "shopify"), {(claim.kind, claim.value.casefold()) for claim in claims})
        self.assertIn((ClaimKind.version, "os 2.0"), {(claim.kind, claim.value.casefold()) for claim in claims})
        self.assertNotIn(ClaimKind.named_entity, {claim.kind for claim in claims})
        self.assertNotIn(ClaimKind.acronym, {claim.kind for claim in claims})

    def test_title_case_integration_terms_are_not_named_entities(self):
        claims = extract_factual_claims("Shopify Third-Party API Integration (Payment, Shipping, CRM).")

        values = {(claim.kind, claim.value.casefold()) for claim in claims}
        self.assertIn((ClaimKind.technology, "shopify"), values)
        self.assertIn((ClaimKind.acronym, "api"), values)
        self.assertIn((ClaimKind.acronym, "crm"), values)
        self.assertNotIn(ClaimKind.named_entity, {claim.kind for claim in claims})

    def test_version_spacing_and_parenthetical_category_rewrites_are_preserved(self):
        version_comparison = compare_factual_claims(
            "Custom Shopify Theme Development with OS 2.0 Section/Block Architecture.",
            "Developed Shopify themes using OS2.0 section/block architecture.",
        )
        labelled_version_comparison = compare_factual_claims(
            "Custom Shopify Theme Development with OS 2.0 Section/Block Architecture.",
            "Developed Shopify themes using OS version 2.0 section/block architecture.",
        )
        expanded_version_comparison = compare_factual_claims(
            "Custom Shopify Theme Development with OS 2.0 Section/Block Architecture.",
            "Leveraging Shopify's Online Store 2.0 section/block architecture.",
        )
        category_comparison = compare_factual_claims(
            "Shopify Third-Party API Integration (Payment, Shipping, CRM).",
            "Integrated Shopify third-party APIs for payment gateways, shipping providers, and CRM systems.",
        )
        changed_version = compare_factual_claims(
            "Custom Shopify Theme Development with OS 2.0 Section/Block Architecture.",
            "Developed Shopify themes using OS3.0 section/block architecture.",
        )

        self.assertEqual(version_comparison.missing_claims, [])
        self.assertEqual(version_comparison.introduced_claims, [])
        self.assertEqual(version_comparison.introduced_material_content, [])
        self.assertEqual(labelled_version_comparison.missing_claims, [])
        self.assertEqual(labelled_version_comparison.introduced_claims, [])
        self.assertEqual(expanded_version_comparison.missing_claims, [])
        self.assertEqual(expanded_version_comparison.introduced_claims, [])
        self.assertEqual(expanded_version_comparison.introduced_material_content, [])
        self.assertEqual(category_comparison.missing_claims, [])
        self.assertEqual(category_comparison.introduced_claims, [])
        self.assertEqual(category_comparison.introduced_material_content, [])
        self.assertIn(ClaimKind.version, {claim.kind for claim in changed_version.missing_claims})


if __name__ == "__main__":
    unittest.main()
