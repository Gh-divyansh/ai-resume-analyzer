"""Deterministic healthcare rollout validation; runs without network or Gemini."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.competency_packs import load_active_nontechnical_packs
from app.services.domain_pack_evaluator import evaluate_domain_pack_projection
from app.services.job_matcher import match_resume_to_job

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "healthcare_validation.json"
REPORT_PATH = Path(__file__).parent / "reports" / "healthcare_validation.json"


def run_validation() -> dict:
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    healthcare = [pack for pack in load_active_nontechnical_packs() if pack.pack_id == "healthcare-core"]
    totals, categories = Counter(), defaultdict(Counter)
    failures = []
    for fixture in fixtures:
        first = evaluate_domain_pack_projection(fixture["resume"], fixture["jd"], packs=healthcare)
        second = evaluate_domain_pack_projection(fixture["resume"], fixture["jd"], packs=healthcare)
        production = match_resume_to_job(fixture["resume"], fixture["jd"])
        expected_matched, expected_missing = set(fixture["expected_matched"]), set(fixture["expected_missing"])
        actual_matched, actual_missing = set(first["matched"]), set(first["missing"])
        reasons = []
        if first != second:
            reasons.append("non_deterministic_projection")
        if actual_matched != expected_matched:
            reasons.append("matched_evidence_mismatch")
        if actual_missing != expected_missing:
            reasons.append("missing_requirement_mismatch")
        for skill in fixture.get("expected_technical", []):
            if skill not in production["matched_skills"]:
                reasons.append("technical_evidence_missing")
        # Production fields must surface scored active requirements when present.
        for record in first["requirements"]:
            if record.canonical_id in actual_missing and record.category.value not in {"role", "seniority", "responsibility"} and record.display_name not in production["missing_skills"]:
                reasons.append("production_missing_not_exposed")
        correct = not reasons
        totals["total"] += 1
        totals["correct" if correct else "incorrect"] += 1
        totals["false_positive"] += len(actual_matched - expected_matched)
        totals["false_negative"] += len(expected_matched - actual_matched)
        category = categories[fixture["category"]]
        category["total"] += 1
        category["correct" if correct else "incorrect"] += 1
        if reasons:
            failures.append({"case": fixture["name"], "category": fixture["category"], "reasons": reasons, "expected_matched": sorted(expected_matched), "actual_matched": sorted(actual_matched), "expected_missing": sorted(expected_missing), "actual_missing": sorted(actual_missing)})
    return {"scope": "offline active healthcare validation", "total_cases": totals["total"], "correct": totals["correct"], "false_positives": totals["false_positive"], "false_negatives": totals["false_negative"], "per_category": {name: dict(values) for name, values in categories.items()}, "failing_cases": failures}


def main() -> None:
    report = run_validation()
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Healthcare validation: {report['correct']}/{report['total_cases']} correct")
    print(f"False positives: {report['false_positives']}; false negatives: {report['false_negatives']}")
    for category, result in report["per_category"].items():
        print(f"- {category}: {result.get('correct', 0)}/{result['total']}")
    if report["failing_cases"]:
        print("Failures:")
        for failure in report["failing_cases"]:
            print(f"- {failure['case']}: {', '.join(failure['reasons'])}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
