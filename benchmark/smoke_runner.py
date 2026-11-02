"""Run explicitly synthetic smoke cases through the production PlanningRunner.

This runner checks wiring and honest UNKNOWN/fake markers only. Its output is not
a quality benchmark and must not be used for promotion decisions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNTIME_SRC = ROOT / "agent-runtime" / "src"
if str(AGENT_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_RUNTIME_SRC))

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import PlanningAnswer, PlanningRequest
from agent_runtime.api.settings import Settings
from agent_runtime.application.budget import Budget
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.run_manifest import RunIdentity, build_run_manifest

SMOKE_CASES = ROOT / "benchmark" / "cases" / "smoke"


class SmokeCheck(BaseModel):
    checkId: str
    status: Literal["PASS", "FAIL", "UNKNOWN", "NOT_ASSESSED"]
    expected: Any = None
    observed: Any = None


class SmokeCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caseId: str
    executionStatus: Literal["COMPLETED", "NOT_RUN", "FAILED"]
    assessmentStatus: Literal["SMOKE_PASS", "SMOKE_FAIL", "UNKNOWN", "NOT_ASSESSED"]
    provenance: str
    reason: str | None = None
    decision: str | None = None
    planningAnswer: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    checks: list[SmokeCheck]


class SmokeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reportType: Literal["SYNTHETIC_SMOKE_NOT_QUALITY_EVALUATION"]
    runId: str
    manifest: dict[str, Any]
    cases: list[SmokeCaseResult]


def _not_run(case: dict[str, Any], reason: str) -> SmokeCaseResult:
    return SmokeCaseResult(
        caseId=str(case.get("caseId", "UNKNOWN")),
        executionStatus="NOT_RUN",
        assessmentStatus="NOT_ASSESSED",
        provenance=str(case.get("provenance", "UNKNOWN")),
        reason=reason,
        checks=[],
    )


def run_case(case: dict[str, Any], *, app, run_id: str) -> SmokeCaseResult:
    """Execute one supported synthetic planning request with the app's runner."""
    if case.get("provenance") != "SYNTHETIC_FICTION":
        return _not_run(case, "非明确标记的虚构输入，本 smoke runner 不读取")
    if case.get("kind") != "planning-request":
        return _not_run(case, "当前 smoke runner 只支持 planning-request fixture")
    if not isinstance(app.state.tool_client, TypedFakeToolClient):
        return _not_run(case, "本 smoke runner 只允许使用类型化假工具")

    try:
        request = PlanningRequest.model_validate(case.get("request"))
        settings = app.state.settings
        context = ExecutionContext(
            subject_id="smoke:synthetic",
            request_id=f"{run_id}:{case['caseId']}",
            curriculum_snapshot_id=request.curriculumSnapshotId,
            offering_snapshot_id=request.offeringSnapshotId,
            model_id=settings.model_id,
            temperature=settings.temperature,
            deadline=datetime.now(UTC) + timedelta(milliseconds=settings.deadline_ms),
            harness_version=app.state.harness.version,
        )
        answer: PlanningAnswer = app.state.runner.run(request, context)
    except Exception as exc:  # noqa: BLE001 —— 本意：任何异常都记成失败证据，不得变成通过
        return SmokeCaseResult(
            caseId=str(case.get("caseId", "UNKNOWN")),
            executionStatus="FAILED",
            assessmentStatus="SMOKE_FAIL",
            provenance="SYNTHETIC_FICTION",
            reason=f"{type(exc).__name__}: {exc}",
            checks=[],
        )

    expected = case.get("syntheticExpectations")
    if not isinstance(expected, dict):
        return SmokeCaseResult(
            caseId=str(case["caseId"]),
            executionStatus="COMPLETED",
            assessmentStatus="NOT_ASSESSED",
            provenance="SYNTHETIC_FICTION",
            decision=answer.decision,
            planningAnswer=answer.model_dump(mode="json"),
            usage=answer.usage.model_dump(mode="json"),
            checks=[],
        )

    unknown_codes = {issue.code for issue in answer.unknowns}
    recommendation_verdicts = [rec.verification.verdict for rec in answer.recommendations]
    expected_verdict = expected.get("verifierVerdict")
    if not recommendation_verdicts and expected_verdict is None:
        verdict_check = SmokeCheck(
            checkId="verifier-verdict",
            status="PASS",
            expected=None,
            observed=None,
        )
    elif not recommendation_verdicts:
        verdict_check = SmokeCheck(
            checkId="verifier-verdict",
            status="UNKNOWN",
            expected=expected_verdict,
            observed=None,
        )
    else:
        verdict_ok = all(value == expected_verdict for value in recommendation_verdicts)
        verdict_check = SmokeCheck(
            checkId="verifier-verdict",
            status="PASS" if verdict_ok else "FAIL",
            expected=expected_verdict,
            observed=recommendation_verdicts,
        )

    checks = [
        SmokeCheck(
            checkId="decision-shape",
            status="PASS" if answer.decision == expected.get("decision") else "FAIL",
            expected=expected.get("decision"),
            observed=answer.decision,
        ),
        verdict_check,
    ]
    for code in expected.get("requiredUnknownCodes", []):
        checks.append(
            SmokeCheck(
                checkId=f"unknown-code:{code}",
                status="PASS" if code in unknown_codes else "FAIL",
                expected=code,
                observed=sorted(unknown_codes),
            )
        )

    statuses = {check.status for check in checks}
    if "FAIL" in statuses:
        assessment = "SMOKE_FAIL"
    elif "UNKNOWN" in statuses:
        assessment = "UNKNOWN"
    else:
        assessment = "SMOKE_PASS"
    return SmokeCaseResult(
        caseId=str(case["caseId"]),
        executionStatus="COMPLETED",
        assessmentStatus=assessment,
        provenance="SYNTHETIC_FICTION",
        decision=answer.decision,
        planningAnswer=answer.model_dump(mode="json"),
        usage=answer.usage.model_dump(mode="json"),
        checks=checks,
    )


def run_smoke(cases: list[dict[str, Any]], *, run_id: str = "smoke:local") -> SmokeReport:
    """Run cases using one local app configured with fake model and fake tools."""
    settings = Settings(
        use_fake_tools=True,
        java_base_url=None,
        model_base_url=None,
        model_api_key="",
        model_id="FAKE_MODEL_DEMO",
        temperature=0.0,
    )
    app = create_app(settings)
    budget = Budget(
        max_input_tokens=settings.max_input_tokens,
        max_output_tokens=settings.max_output_tokens,
        max_tool_calls=settings.max_tool_calls,
        max_model_calls=settings.max_model_calls,
        deadline_ms=settings.deadline_ms,
    )
    representative = cases[0] if cases else {}
    request_data = representative.get("request", {})
    curriculum_id = str(request_data.get("curriculumSnapshotId", "synthetic:unset"))
    offering_id = request_data.get("offeringSnapshotId")
    manifest_context = ExecutionContext(
        subject_id="smoke:synthetic",
        request_id=f"{run_id}:manifest",
        curriculum_snapshot_id=curriculum_id,
        offering_snapshot_id=offering_id,
        model_id=settings.model_id,
        temperature=settings.temperature,
        deadline=datetime.now(UTC) + timedelta(milliseconds=settings.deadline_ms),
        harness_version=app.state.harness.version,
    )
    manifest = build_run_manifest(
        context=manifest_context,
        identity=RunIdentity(
            verifier_version="verifier:fake",
            benchmark_set_version="synthetic-smoke:v1",
            evaluator_version="synthetic-structure-checks:v1",
        ),
        budget=budget,
        run_id=run_id,
    )
    results = [run_case(case, app=app, run_id=run_id) for case in cases]
    return SmokeReport(
        reportType="SYNTHETIC_SMOKE_NOT_QUALITY_EVALUATION",
        runId=run_id,
        manifest=manifest.model_dump(mode="json"),
        cases=results,
    )


def load_cases(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        paths = [path]
    else:
        paths = sorted(path.glob("*.json"))
    cases = []
    for case_path in paths:
        value = json.loads(case_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            # 校验的是案例文件的内容，不是函数入参的类型契约，
            # 所以这里用 ValueError 而不是 TypeError。
            raise ValueError(f"{case_path}: smoke case must be an object")  # noqa: TRY004
        cases.append(value)
    return cases


def report_exit_code(report: SmokeReport) -> int:
    """Only a non-empty set of completed smoke checks with no unknowns is success."""
    if not report.cases:
        return 1
    return (
        0
        if all(case.executionStatus == "COMPLETED" and case.assessmentStatus == "SMOKE_PASS" for case in report.cases)
        else 1
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行明确标记的 CoursePilot 合成 smoke cases")
    parser.add_argument("--cases", type=Path, default=SMOKE_CASES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_smoke(load_cases(args.cases))
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return report_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
