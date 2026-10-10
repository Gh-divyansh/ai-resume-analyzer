"""Offline fixture evaluation for the side-by-side universal AI matcher."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.universal_match import UniversalAIAnalysis
from app.services.universal_ai_matcher import _resume_sections, match_resume_to_job_universal

FIXTURES = Path(__file__).parent / "fixtures" / "universal_ai_evaluation.json"
REPORT = Path(__file__).parent / "reports" / "universal_ai_evaluation.json"


def _analysis(case: dict) -> UniversalAIAnalysis:
    requirements = []
    for item in case["requirements"]:
        identifier, label, category, priority, years, section, quote, strength = item
        requirements.append({"id": identifier, "label": label, "category": category, "priority": priority, "minimum_years": years, "evidence": [{"source_section": section, "quote": quote, "strength": strength, "explanation": "Fixture-provided semantic assessment."}], "explanation": "Fixture-provided requirement assessment."})
    return UniversalAIAnalysis.model_validate({"requirements": requirements, "overall_explanation": "Offline synthetic evaluation."})


def _grounding_errors(result: dict, resume: dict) -> list[str]:
    sections = _resume_sections(resume)
    errors = []
    for requirement in result["ai_requirements"]:
        for evidence in requirement["evidence"]:
            quote = evidence["quote"].casefold()
            present = any(quote in text.casefold() for text in sections.get(evidence["source_section"], []))
            if evidence["strength"] not in {"none", "keyword_only"} and not present:
                errors.append(f"ungrounded_citation:{requirement['id']}")
    return errors


def run_evaluation() -> dict:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    totals, domains, distribution = Counter(), defaultdict(Counter), Counter()
    failures, human_review, repeated_differences = [], [], []
    for case in cases:
        ai = _analysis(case)
        with patch("app.services.universal_ai_matcher.extract_universal_ai_analysis", return_value=ai):
            first = match_resume_to_job_universal(case["resume"], case["jd"])
            second = match_resume_to_job_universal(case["resume"], case["jd"])
        actual_matched = {item["id"] for item in first["ai_requirements"] if item["label"] in first["matched_skills"] or any(item["label"] in line for line in first["matching_experience"])}
        # The API's legacy-compatible fields omit seniority/responsibility IDs,
        # so determine expected status from validated missing/matched labels.
        expected_matched = set(case["matched"])
        missing_labels = set(first["missing_skills"]) | {gap.removeprefix("The resume does not document evidence for ").removesuffix(".") for gap in first["gaps"]}
        expected_missing = {item[0] for item in case["requirements"]} - expected_matched
        id_to_label = {item[0]: item[1] for item in case["requirements"]}
        actual_missing = {identifier for identifier, label in id_to_label.items() if label in missing_labels}
        errors = _grounding_errors(first, case["resume"])
        if first != second:
            errors.append("repeated_call_difference")
            repeated_differences.append(case["name"])
        if actual_matched != expected_matched:
            errors.append("semantic_match_mismatch")
        if actual_missing != expected_missing:
            errors.append("missing_requirement_mismatch")
        required = {item[0] for item in case["requirements"] if item[3] == "required"}
        preferred = {item[0] for item in case["requirements"] if item[3] == "preferred"}
        returned_required = set(first["requirements"]["required"])
        returned_preferred = set(first["requirements"]["preferred"])
        if any(id_to_label[item] not in returned_required for item in required) or any(id_to_label[item] not in returned_preferred for item in preferred):
            errors.append("priority_classification_mismatch")
        passed = not errors
        totals["total"] += 1
        totals["passed" if passed else "failed"] += 1
        totals["validation_errors"] += len(errors)
        domains[case["domain"]]["total"] += 1
        domains[case["domain"]]["passed" if passed else "failed"] += 1
        distribution[f"{first['match_score']//10*10}-{min(first['match_score']//10*10 + 9, 100)}"] += 1
        if errors:
            failures.append({"case": case["name"], "domain": case["domain"], "reasons": errors, "expected_matched": sorted(expected_matched), "actual_matched": sorted(actual_matched), "expected_missing": sorted(expected_missing), "actual_missing": sorted(actual_missing)})
        # Semantic classifications and any inferred/keyword-only evidence remain
        # review items even when the deterministic validator safely rejects them.
        if case["scenario"] in {"semantic_wording", "similar_but_different", "keyword_only", "mixed_technical_nontechnical"}:
            human_review.append(case["name"])
    return {"label": "synthetic offline validation only; not real-world accuracy", "total_cases": totals["total"], "passed": totals["passed"], "failed": totals["failed"], "validation_errors": totals["validation_errors"], "per_domain": {name: dict(value) for name, value in domains.items()}, "score_distribution": dict(distribution), "repeated_call_differences": repeated_differences, "cases_requiring_human_review": human_review, "detailed_failures": failures}


def main() -> None:
    report = run_evaluation()
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Universal AI synthetic evaluation: {report['passed']}/{report['total_cases']} passed")
    print(f"Validation errors: {report['validation_errors']}; repeated differences: {len(report['repeated_call_differences'])}")
    for domain, metrics in report["per_domain"].items():
        print(f"- {domain}: {metrics.get('passed', 0)}/{metrics['total']}")
    print(f"Human review: {', '.join(report['cases_requiring_human_review']) or 'none'}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
