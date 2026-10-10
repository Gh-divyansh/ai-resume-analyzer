"""Run fixed, offline calibration scenarios for every inactive domain pack.

Run from ``backend``:
    $env:PYTHONPATH = "$PWD\\venv\\Lib\\site-packages"; py -3.14 tests/run_domain_evaluation.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Direct script execution places ``tests`` on sys.path. Add backend explicitly
# so this remains a simple documented offline command.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.domain_pack_evaluator import evaluate_domain_pack_projection
from app.services.competency_packs import load_nontechnical_packs


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "domain_pack_evaluation.json"
REPORT_PATH = Path(__file__).parent / "reports" / "domain_pack_evaluation.json"


def _resume(*, title="Candidate", skills=None, responsibilities=None, duration="2020 - 2024", summary="", education=None, projects=None):
    return {
        "title": title,
        "summary": summary,
        "skills": skills or [],
        "experience": [{"role": title, "duration": duration, "responsibilities": responsibilities or []}],
        "education": education or [],
        "projects": projects or [],
    }


def _cases(domain: dict) -> list[dict]:
    """Fixed scenarios and expected ground truth; no random data is generated."""

    first, second = domain["skills"]
    credential = domain["credential"]
    prefix = domain["pack"].split("-")[0]
    required = [first, second, credential]
    return [
        {"name":"strong_match", "relationship":"strong", "jd":f"{first}, {second}, and {credential} required.", "resume":_resume(skills=[credential], responsibilities=[first, second]), "required":required, "missing":[], "credential":"met", "experience":"met", "seniority":"not_required", "should_count":[first, second, credential], "should_not_count_alone":[]},
        {"name":"medium_match", "relationship":"medium", "jd":f"{first}, {second}, and {credential} required.", "resume":_resume(responsibilities=[first]), "required":required, "missing":[second, credential], "credential":"missing", "experience":"met", "seniority":"not_required", "should_count":[first], "should_not_count_alone":[]},
        {"name":"weak_match", "relationship":"weak", "jd":f"{first} and {credential} required.", "resume":_resume(responsibilities=[]), "required":[first, credential], "missing":[first, credential], "credential":"missing", "experience":"missing", "seniority":"not_required", "should_count":[], "should_not_count_alone":[]},
        {"name":"unrelated_candidate", "relationship":"unrelated", "jd":f"{first} and {credential} required.", "resume":_resume(responsibilities=["unrelated inventory work"]), "required":[first, credential], "missing":[first, credential], "credential":"missing", "experience":"missing", "seniority":"not_required", "should_count":[], "should_not_count_alone":["unrelated inventory work"]},
        {"name":"missing_required_skill", "relationship":"gap", "jd":f"{first}, {second}, and {credential} required.", "resume":_resume(skills=[credential], responsibilities=[first]), "required":required, "missing":[second], "credential":"met", "experience":"met", "seniority":"not_required", "should_count":[first, credential], "should_not_count_alone":[]},
        {"name":"missing_required_credential", "relationship":"gap", "jd":f"{first} and {credential} required.", "resume":_resume(responsibilities=[first]), "required":[first, credential], "missing":[credential], "credential":"missing", "experience":"met", "seniority":"not_required", "should_count":[first], "should_not_count_alone":[f"familiar with {credential} terminology"]},
        {"name":"insufficient_experience", "relationship":"gap", "jd":f"3+ years {first} experience required.", "resume":_resume(responsibilities=[first], duration="2023 - 2024"), "required":[first], "missing":[first], "credential":"not_required", "experience":"missing", "seniority":"not_required", "should_count":[], "should_not_count_alone":[first]},
        {"name":"seniority_mismatch", "relationship":"gap", "jd":f"Senior {first} required.", "resume":_resume(responsibilities=[first, "led daily handovers"]), "required":[first, "seniority.senior"], "missing":["seniority.senior"], "credential":"not_required", "experience":"met", "seniority":"missing", "should_count":[first], "should_not_count_alone":["led daily handovers"]},
        {"name":"keyword_only_mentions", "relationship":"adversarial", "jd":f"{first} and {credential} required.", "resume":_resume(summary=f"Interested in {first} and familiar with {credential} terminology."), "required":[first, credential], "missing":[first, credential], "credential":"missing", "experience":"missing", "seniority":"not_required", "should_count":[], "should_not_count_alone":[first, credential]},
        {"name":"ordinary_lead_manage_words", "relationship":"adversarial", "jd":f"Senior {first} required.", "resume":_resume(responsibilities=[first, "led and managed daily workflow"]), "required":[first, "seniority.senior"], "missing":["seniority.senior"], "credential":"not_required", "experience":"met", "seniority":"missing", "should_count":[first], "should_not_count_alone":["led", "managed"]},
        {"name":"similar_but_different_skill", "relationship":"adversarial", "jd":f"{first} required.", "resume":_resume(responsibilities=[second]), "required":[first], "missing":[first], "credential":"not_required", "experience":"missing", "seniority":"not_required", "should_count":[], "should_not_count_alone":[second]},
        {"name":"project_evidence", "relationship":"adversarial", "jd":f"{first} required.", "resume":_resume(projects=[{"name":"Documented project", "description":first}]), "required":[first], "missing":[], "credential":"not_required", "experience":"met", "seniority":"not_required", "should_count":[first], "should_not_count_alone":[]},
        {"name":"education_keyword_only", "relationship":"adversarial", "jd":f"{first} required.", "resume":_resume(education=[{"degree":f"Coursework covering {first}"}]), "required":[first], "missing":[first], "credential":"not_required", "experience":"missing", "seniority":"not_required", "should_count":[], "should_not_count_alone":[first]},
    ]


def run_evaluation() -> dict:
    domains = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    alias_ids = {
        alias.casefold(): concept.canonical_id
        for pack in load_nontechnical_packs()
        for concept in pack.concepts
        for alias in concept.aliases
    }
    totals = Counter()
    per_domain = {}
    all_cases = []
    for domain in domains:
        metrics = Counter()
        findings = []
        for case in _cases(domain):
            result = evaluate_domain_pack_projection(case["resume"], case["jd"])
            expected_missing = {alias_ids.get(value.casefold(), value) for value in case["missing"]}
            actual_missing = set(result["missing"])
            correct = expected_missing == actual_missing
            errors = []
            if not correct:
                errors.append("missing_requirement")
            if case["credential"] == "missing" and not any("credential" in item.category.value for item in result["requirements"] if item.canonical_id in actual_missing):
                errors.append("credential")
            if case["experience"] == "missing" and not expected_missing <= actual_missing:
                errors.append("experience")
            if case["seniority"] == "missing" and "seniority.senior" not in actual_missing:
                errors.append("seniority")
            if case["should_not_count_alone"] and not expected_missing <= actual_missing:
                errors.append("evidence_vs_keyword")
            metrics["total"] += 1
            metrics["correct" if correct else "incorrect"] += 1
            metrics["false_negative"] += len(expected_missing - actual_missing)
            metrics["false_positive"] += len(actual_missing - expected_missing)
            for error in errors:
                metrics[f"{error}_errors"] += 1
            findings.append({"case": case["name"], "correct": correct, "expected_missing": sorted(expected_missing), "actual_missing": sorted(actual_missing), "errors": errors})
        # Synthetic correctness is intentionally insufficient for GREEN.
        status = "YELLOW" if metrics["incorrect"] == 0 else "RED"
        per_domain[domain["domain"]] = {"pack": domain["pack"], "status": status, "metrics": dict(metrics), "findings": findings}
        totals.update(metrics)
        all_cases.extend(findings)
    return {"overall": dict(totals), "domains": per_domain, "case_count": len(all_cases), "scope":"offline inactive domain-pack projection only"}


def main() -> None:
    report = run_evaluation()
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Domain-pack evaluation: {report['case_count']} cases")
    for name, value in report["domains"].items():
        metrics = value["metrics"]
        print(f"- {name}: {value['status']} — {metrics.get('correct', 0)}/{metrics.get('total', 0)} correct")
    print(f"Overall: {report['overall'].get('correct', 0)}/{report['overall'].get('total', 0)} correct")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
