import copy
import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.schemas.domain_evidence import (
    EvidenceRecord,
    EvidenceStrength,
    EvidenceType,
    RecordCategory,
    RequirementPriority,
    RequirementRecord,
)
from app.services.competency_packs import alias_map, load_pack, load_technology_core, normalize_pack_alias
from app.services.job_matcher import SKILL_ALIASES
from app.services.technology_core_evaluator import (
    build_technology_evidence_records,
    build_technology_requirement_records,
    evaluate_technology_core_parity,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))


class DomainEvidenceModelTests(unittest.TestCase):
    def test_domain_neutral_records_construct_with_strict_enums(self):
        requirement = RequirementRecord(
            canonical_id="healthcare.patient_care",
            display_name="Patient care",
            category=RecordCategory.competency,
            priority=RequirementPriority.required,
            evidence_type=EvidenceType.responsibility,
            source_text="Provide patient care.",
            pack="healthcare-core",
            pack_version="1",
        )
        evidence = EvidenceRecord(
            canonical_id="healthcare.patient_care",
            display_name="Patient care",
            category=RecordCategory.competency,
            evidence_type=EvidenceType.responsibility,
            strength=EvidenceStrength.direct_responsibility,
            source_text="Provided inpatient patient care.",
            source_section="experience",
            source_reference="experience[0].responsibilities[0]",
        )

        self.assertEqual(requirement.priority, RequirementPriority.required)
        self.assertEqual(evidence.strength, EvidenceStrength.direct_responsibility)

    def test_invalid_record_is_rejected(self):
        with self.assertRaises(ValidationError):
            RequirementRecord(
                canonical_id="x",
                display_name="",
                category="unknown",
                priority="mandatory",
                evidence_type="tool",
                source_text="",
                pack="",
                pack_version="",
            )

    def test_technology_core_loads_and_exactly_matches_current_aliases(self):
        pack = load_technology_core()

        self.assertEqual((pack.pack_id, pack.version, pack.namespace), ("technology-core", "1", "technology"))
        self.assertEqual(alias_map(pack), {name: tuple(aliases) for name, aliases in SKILL_ALIASES.items()})

    def test_alias_normalization_is_deterministic(self):
        self.assertEqual(normalize_pack_alias("  React.js\t"), "react.js")
        self.assertEqual(normalize_pack_alias("REST   APIs"), "rest apis")

    def test_pack_validation_rejects_duplicate_aliases_and_invalid_metadata(self):
        valid_payload = load_technology_core().model_dump(mode="json")
        duplicate_alias_payload = copy.deepcopy(valid_payload)
        duplicate_alias_payload["concepts"][1]["aliases"].append("python")
        invalid_metadata_payload = copy.deepcopy(valid_payload)
        invalid_metadata_payload["pack_id"] = "Technology Core"

        for payload, expected_message in (
            (duplicate_alias_payload, "maps ambiguously"),
            (invalid_metadata_payload, "pack_id"),
        ):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected_message):
                    load_pack(path)

    def test_side_by_side_parity_matches_all_calibration_fixtures(self):
        for name in (
            "strong_match",
            "medium_match",
            "weak_match",
            "missing_required_skills",
            "seniority_mismatch",
            "experience_mismatch",
        ):
            fixture = load_fixture(name)
            evaluation = evaluate_technology_core_parity(fixture["resume"], fixture["job_description"])

            self.assertTrue(all(evaluation["parity"].values()), name)
            self.assertGreaterEqual(evaluation["record_counts"]["requirements"], 0, name)
            self.assertGreaterEqual(evaluation["record_counts"]["evidence"], 0, name)

    def test_cross_domain_fixtures_are_structurally_representable(self):
        fixtures = json.loads((FIXTURE_DIRECTORY / "domain_audit.json").read_text(encoding="utf-8"))

        for fixture in fixtures:
            resume = fixture["resume"]
            job_description = fixture["job_description"]
            records = build_technology_requirement_records(job_description)
            evidence = build_technology_evidence_records(resume)
            category = RecordCategory.competency
            requirement = RequirementRecord(
                canonical_id=f"audit.{fixture['domain'].lower().replace(' ', '_').replace('/', '_')}",
                display_name=fixture["domain"],
                category=category,
                priority=RequirementPriority.required,
                evidence_type=EvidenceType.responsibility,
                source_text=job_description,
                pack="audit-structural",
                pack_version="1",
            )
            source_text = fixture["resume"]["summary"] or fixture["resume"]["title"]
            evidence_record = EvidenceRecord(
                canonical_id=requirement.canonical_id,
                display_name=requirement.display_name,
                category=category,
                evidence_type=EvidenceType.responsibility,
                strength=EvidenceStrength.keyword_mention,
                source_text=source_text,
                source_section="summary",
                source_reference="summary",
            )

            self.assertIsInstance(records, list, fixture["domain"])
            self.assertIsInstance(evidence, list, fixture["domain"])
            self.assertEqual(requirement.canonical_id, evidence_record.canonical_id, fixture["domain"])


if __name__ == "__main__":
    unittest.main()
