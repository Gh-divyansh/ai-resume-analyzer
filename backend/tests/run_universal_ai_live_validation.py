"""Live Gemini validation for `/api/resume/match-ai`; never run in unit tests.

Run from backend with a configured GEMINI_API_KEY:
    $env:PYTHONPATH = "$PWD\\venv\\Lib\\site-packages"; py -3.14 tests/run_universal_ai_live_validation.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.job_matcher import match_resume_to_job
from app.services.universal_ai_matcher import (
    UniversalAIGenerationError,
    _resume_sections,
    match_resume_to_job_universal_with_metadata,
)

FIXTURES = Path(__file__).parent / "fixtures" / "universal_ai_live_review.json"
REPORT = Path(__file__).parent / "reports" / "universal_ai_live_validation.json"
RUNS_PER_CASE = 3
CALL_DELAY_SECONDS = 2


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _contains_observation(values: list[str], observation: str) -> bool:
    expected = _norm(observation)
    return any(expected in _norm(value) or _norm(value) in expected for value in values if value)


def _citation_errors(result: dict, resume: dict) -> list[str]:
    sections = _resume_sections(resume)
    errors = []
    for requirement in result.get("ai_requirements", []):
        for evidence in requirement.get("evidence", []):
            quote = evidence.get("quote", "").casefold()
            strength = evidence.get("strength")
            present = any(quote and quote in item.casefold() for item in sections.get(evidence.get("source_section", ""), []))
            if strength not in {"none", "keyword_only"} and not present:
                errors.append(f"ungrounded_citation:{requirement.get('id')}")
    return errors


def _signature(result: dict) -> dict:
    return {"requirements": [(item["label"], item["category"], item["priority"], item["minimum_years"], [(e["source_section"], e["quote"], e["strength"]) for e in item["evidence"]]) for item in result.get("ai_requirements", [])], "score": result.get("match_score"), "explanation": result.get("ai_overall_explanation")}


def _variance_dimensions(results: list[dict]) -> dict[str, bool]:
    """Measure structural AI variance independently from explanatory prose."""

    requirements = [
        [(item["label"], item["category"], item["minimum_years"]) for item in result.get("ai_requirements", [])]
        for result in results
    ]
    priorities = [
        [(item["label"], item["priority"]) for item in result.get("ai_requirements", [])]
        for result in results
    ]
    evidence = [
        [
            (item["label"], evidence["source_section"], evidence["quote"], evidence["strength"])
            for item in result.get("ai_requirements", [])
            for evidence in item.get("evidence", [])
        ]
        for result in results
    ]
    return {
        "requirements": len({json.dumps(item, sort_keys=True) for item in requirements}) > 1,
        "priorities": len({json.dumps(item, sort_keys=True) for item in priorities}) > 1,
        "evidence": len({json.dumps(item, sort_keys=True) for item in evidence}) > 1,
    }


def run_live_validation() -> dict:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))
    totals, domains = Counter(), defaultdict(Counter)
    failures, mismatches, legacy_differences, human_review = [], [], [], []
    score_distribution, variance, variance_totals = Counter(), [], Counter()
    for case in cases:
        results, errors, retries = [], [], 0
        for attempt in range(RUNS_PER_CASE):
            try:
                result, metadata = match_resume_to_job_universal_with_metadata(case["resume"], case["jd"])
                retries += metadata.retries
                errors.extend(_citation_errors(result, case["resume"]))
                results.append(result)
            except UniversalAIGenerationError as error:
                kind = "transport" if error.transient else error.kind
                errors.append(f"call_{attempt + 1}_{kind}_failed:{type(error).__name__}")
                retries += max(error.attempts - 1, 0)
            except Exception as error:
                errors.append(f"call_{attempt + 1}_model_quality_failed:{type(error).__name__}")
            if attempt < RUNS_PER_CASE - 1:
                time.sleep(CALL_DELAY_SECONDS)
        totals["calls"] += RUNS_PER_CASE
        totals["successful_calls"] += len(results)
        totals["retries"] += retries
        if len(results) == RUNS_PER_CASE:
            totals["complete_cases"] += 1
        else:
            totals["incomplete_cases"] += 1
        deterministic_errors = [item for item in errors if item.startswith("ungrounded")]
        format_errors = [item for item in errors if "format_failed" in item or "model_quality" in item]
        transport_errors = [item for item in errors if "transport" in item]
        totals["validation_errors"] += len(deterministic_errors)
        totals["transport_failures"] += len(transport_errors)
        totals["model_quality_failures"] += len(format_errors)
        if not results:
            failures.append({"case": case["name"], "domain": case["domain"], "reasons": errors})
            totals["validation_failures"] += 1
            continue
        result = results[0]
        signatures = [_signature(item) for item in results]
        if len({json.dumps(item, sort_keys=True) for item in signatures}) > 1:
            dimensions = _variance_dimensions(results)
            variance.append({"case": case["name"], "dimensions": dimensions, "signatures": signatures})
            for dimension, changed in dimensions.items():
                variance_totals[dimension] += int(changed)
        expected = case["expected"]
        returned_required = result["requirements"]["required"]
        returned_preferred = result["requirements"]["preferred"]
        returned_evidence = [evidence["quote"] for requirement in result.get("ai_requirements", []) for evidence in requirement.get("evidence", []) if evidence.get("strength") not in {"none", "keyword_only"}]
        returned_missing = result["missing_skills"] + result["gaps"]
        observations = []
        for item in expected["required"]:
            if not _contains_observation(returned_required, item): observations.append(f"missing_required_observation:{item}")
        for item in expected["preferred"]:
            if not _contains_observation(returned_preferred, item): observations.append(f"missing_preferred_observation:{item}")
        for item in expected["evidence"]:
            if not _contains_observation(returned_evidence, item): observations.append(f"missing_evidence_observation:{item}")
        for item in expected["missing"]:
            if not _contains_observation(returned_missing, item): observations.append(f"missing_gap_observation:{item}")
        if deterministic_errors or format_errors:
            failures.append({"case": case["name"], "domain": case["domain"], "reasons": deterministic_errors + format_errors})
        if observations:
            mismatches.append({"case": case["name"], "domain": case["domain"], "observations": observations, "classification": "AI interpretation disagreement; requires human review"})
        legacy = match_resume_to_job(case["resume"], case["jd"])
        if legacy["match_score"] != result["match_score"] or set(legacy["matched_skills"]) != set(result["matched_skills"]):
            legacy_differences.append({"case": case["name"], "legacy_score": legacy["match_score"], "ai_score": result["match_score"], "legacy_matched": legacy["matched_skills"], "ai_matched": result["matched_skills"]})
        if observations or case["domain"] in {"healthcare", "sales", "design", "logistics"}:
            human_review.append(case["name"])
        score_distribution[f"{result['match_score']//10*10}-{min(result['match_score']//10*10+9, 100)}"] += 1
        domains[case["domain"]]["cases"] += 1
        domains[case["domain"]]["successful_calls"] += len(results)
    return {"label":"live Gemini evaluation on realistic synthetic data; not real-world accuracy", "total_cases": len(cases), "calls_requested": len(cases) * RUNS_PER_CASE, "successful_calls": totals["successful_calls"], "complete_cases_3_of_3": totals["complete_cases"], "incomplete_cases": totals["incomplete_cases"], "retries": totals["retries"], "transport_failures": totals["transport_failures"], "malformed_outputs": totals["model_quality_failures"], "model_quality_failures": totals["model_quality_failures"], "validation_failures": totals["validation_failures"], "validation_errors": totals["validation_errors"], "per_domain": {name: dict(value) for name, value in domains.items()}, "score_distribution": dict(score_distribution), "repeated_call_variance": variance, "requirement_variance_cases": variance_totals["requirements"], "priority_variance_cases": variance_totals["priorities"], "evidence_variance_cases": variance_totals["evidence"], "human_review_mismatches": mismatches, "legacy_vs_ai_differences": legacy_differences, "important_false_positives": [item for item in failures if "ungrounded" in " ".join(item["reasons"])], "important_false_negatives": mismatches, "cases_ai_appears_better_than_legacy": [item["case"] for item in legacy_differences if item["ai_score"] > item["legacy_score"]], "cases_ai_appears_worse_than_legacy": [item["case"] for item in legacy_differences if item["ai_score"] < item["legacy_score"]], "cases_requiring_manual_review": sorted(set(human_review)), "detailed_failures": failures}


def main() -> None:
    report = run_live_validation()
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Live universal AI validation: {report['successful_calls']}/{report['calls_requested']} calls succeeded")
    print(f"Transport failures: {report['transport_failures']}; retries: {report['retries']}; variance cases: {len(report['repeated_call_variance'])}")
    print(f"Human-review mismatches: {len(report['human_review_mismatches'])}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
