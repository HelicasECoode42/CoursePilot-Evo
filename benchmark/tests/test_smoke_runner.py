from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from smoke_runner import SmokeCaseResult, load_cases, report_exit_code, run_smoke


def test_synthetic_case_runs_through_production_runner_and_reports_unknowns() -> None:
    cases = load_cases(ROOT / "benchmark" / "cases" / "smoke")
    report = run_smoke(cases, run_id="smoke:test-001")

    assert report.reportType == "SYNTHETIC_SMOKE_NOT_QUALITY_EVALUATION"
    assert report.manifest["verifierVersion"] == "verifier:fake"
    result = report.cases[0]
    assert result.executionStatus == "COMPLETED"
    assert result.assessmentStatus == "SMOKE_PASS"
    assert result.decision == "RECOMMENDATIONS"
    assert result.usage is not None
    assert result.usage["inputTokens"] is None
    assert result.usage["outputTokens"] is None
    assert all(rec["verification"]["verdict"] == "UNKNOWN" for rec in result.planningAnswer["recommendations"])
    assert any(check.checkId == "unknown-code:FAKE_MODEL" and check.status == "PASS" for check in result.checks)


def test_unsupported_fixture_is_not_run_and_not_scored() -> None:
    report = run_smoke(
        [{"caseId": "G1-001", "provenance": "SYNTHETIC_FICTION", "kind": "academic-record"}],
        run_id="smoke:test-unsupported",
    )

    result = report.cases[0]
    assert result.executionStatus == "NOT_RUN"
    assert result.assessmentStatus == "NOT_ASSESSED"
    assert result.planningAnswer is None
    assert result.reason == "当前 smoke runner 只支持 planning-request fixture"


def test_non_synthetic_case_is_not_run() -> None:
    report = run_smoke(
        [{"caseId": "G1-001", "provenance": "REAL", "kind": "planning-request"}],
        run_id="smoke:test-real-input",
    )
    assert report.cases[0].executionStatus == "NOT_RUN"
    assert report.cases[0].assessmentStatus == "NOT_ASSESSED"


def test_invalid_planning_request_is_a_failed_execution() -> None:
    report = run_smoke(
        [{"caseId": "SYN-BAD", "provenance": "SYNTHETIC_FICTION", "kind": "planning-request", "request": {}}],
        run_id="smoke:test-invalid",
    )
    assert report.cases[0].executionStatus == "FAILED"
    assert report.cases[0].assessmentStatus == "SMOKE_FAIL"


def test_report_is_serializable_and_keeps_failure_distinct() -> None:
    report = run_smoke(
        [
            {
                "caseId": "SYN-UNKNOWN",
                "provenance": "SYNTHETIC_FICTION",
                "kind": "planning-request",
                "request": {},
            }
        ],
        run_id="smoke:test-json",
    )
    encoded = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["reportType"] == "SYNTHETIC_SMOKE_NOT_QUALITY_EVALUATION"
    assert decoded["cases"][0]["executionStatus"] == "FAILED"
    assert decoded["cases"][0]["usage"] is None


def test_case_json_is_valid() -> None:
    case = load_cases(ROOT / "benchmark" / "cases" / "smoke" / "SYN-001.json")[0]
    assert case["provenance"] == "SYNTHETIC_FICTION"
    assert case["syntheticExpectations"]["verifierVerdict"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("execution", "assessment", "expected"),
    [
        ("COMPLETED", "SMOKE_PASS", 0),
        ("COMPLETED", "UNKNOWN", 1),
        ("NOT_RUN", "NOT_ASSESSED", 1),
        ("FAILED", "SMOKE_FAIL", 1),
    ],
)
def test_exit_code_requires_every_case_to_run_and_pass(execution: str, assessment: str, expected: int) -> None:
    case = SmokeCaseResult(
        caseId="SYN-EXIT",
        executionStatus=execution,
        assessmentStatus=assessment,
        provenance="SYNTHETIC_FICTION",
        checks=[],
    )
    report = run_smoke([], run_id="smoke:empty")
    report.cases.append(case)
    assert report_exit_code(report) == expected


def test_empty_run_is_not_success() -> None:
    assert report_exit_code(run_smoke([], run_id="smoke:empty")) == 1
