"""Capture telemetry from the production runner with an explicitly enabled model endpoint.

This is a wiring/latency baseline over synthetic smoke prompts. It has no labels and
does not assess answer quality or support promotion decisions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNTIME_SRC = ROOT / "agent-runtime" / "src"
if str(AGENT_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_RUNTIME_SRC))

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.model_client import PLACEHOLDER_MODEL_ID
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import PlanningRequest
from agent_runtime.api.settings import Settings, load_settings
from agent_runtime.application.budget import Budget
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.run_manifest import RunIdentity, build_run_manifest

DEFAULT_CASES = ROOT / "benchmark" / "cases" / "smoke"
DEFAULT_SUBJECT_ID = "S001"
DEFAULT_CURRICULUM_SNAPSHOT_ID = "PLAN_CS_2025"


def validate_real_run_settings(settings: Settings, *, enabled: str | None) -> None:
    """Reject accidental fake or unconfigured runs before creating any clients."""
    if enabled != "true":
        raise ValueError("设置 CP_BENCHMARK_ENABLE_REAL_MODEL=true 后才允许调用模型端点")
    if not settings.model_base_url or not settings.model_api_key:
        raise ValueError("需要配置 CP_MODEL_BASE_URL 与 CP_MODEL_API_KEY")
    if not settings.java_base_url or not settings.service_key:
        raise ValueError("需要配置真实 Java 核验服务 CP_JAVA_BASE_URL 与 CP_SERVICE_KEY")
    if settings.use_fake_tools:
        raise ValueError("真实基线不允许启用假工具")
    if settings.model_id == PLACEHOLDER_MODEL_ID:
        raise ValueError("需要配置具体的 CP_MODEL_ID")


def load_synthetic_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    """Load only the public synthetic smoke set; do not accept private benchmark splits."""
    resolved = path.resolve()
    allowed = DEFAULT_CASES.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise ValueError("真实模型基线只接受 benchmark/cases/smoke 下的虚构案例")
    paths = [resolved] if resolved.is_file() else sorted(resolved.glob("*.json"))
    cases = [json.loads(item.read_text(encoding="utf-8")) for item in paths]
    if not cases or any(
        not isinstance(case, dict)
        or case.get("provenance") != "SYNTHETIC_FICTION"
        or case.get("kind") != "planning-request"
        for case in cases
    ):
        raise ValueError("案例集必须非空，且全部为 SYNTHETIC_FICTION planning-request")
    return cases


def run_baseline(
    cases: list[dict[str, Any]],
    *,
    settings: Settings,
    enabled: str | None,
    subject_id: str = DEFAULT_SUBJECT_ID,
    curriculum_snapshot_id: str = DEFAULT_CURRICULUM_SNAPSHOT_ID,
) -> dict[str, Any]:
    """Run synthetic prompts through the production PlanningRunner and retain telemetry only."""
    validate_real_run_settings(settings, enabled=enabled)
    app = create_app(settings)
    if isinstance(app.state.tool_client, TypedFakeToolClient):
        raise TypeError("生产 Runner 未组装真实 Java 工具")

    run_id = f"real-model-baseline:{uuid4()}"
    first_request_data = dict(cases[0].get("request", {}))
    first_request_data["academicRecordId"] = subject_id
    first_request_data["curriculumSnapshotId"] = curriculum_snapshot_id
    first_request = PlanningRequest.model_validate(first_request_data)
    manifest_context = ExecutionContext(
        subject_id=subject_id,
        request_id=f"{run_id}:manifest",
        curriculum_snapshot_id=first_request.curriculumSnapshotId,
        offering_snapshot_id=first_request.offeringSnapshotId,
        model_id=settings.model_id,
        temperature=settings.temperature,
        deadline=datetime.now(UTC) + timedelta(milliseconds=settings.deadline_ms),
        harness_version=app.state.harness.version,
    )
    manifest = build_run_manifest(
        context=manifest_context,
        identity=RunIdentity(
            java_tool_api_version="java.openapi.json:unversioned",
            verifier_version="verifier:configured-version-unpinned",
            benchmark_set_version="synthetic-smoke:v1",
            evaluator_version="evaluator:unavailable-no-labels",
        ),
        budget=Budget(
            max_input_tokens=settings.max_input_tokens,
            max_output_tokens=settings.max_output_tokens,
            max_tool_calls=settings.max_tool_calls,
            max_model_calls=settings.max_model_calls,
            deadline_ms=settings.deadline_ms,
        ),
        run_id=run_id,
    )
    records: list[dict[str, Any]] = []
    for case in cases:
        started = time.monotonic()
        case_id = str(case.get("caseId", "UNKNOWN"))
        try:
            request_data = dict(case.get("request", {}))
            # The checked-in smoke case uses a private fake id; bind it to the
            # Java demo seed selected by the explicit subject/snapshot settings.
            request_data["academicRecordId"] = subject_id
            request_data["curriculumSnapshotId"] = curriculum_snapshot_id
            request = PlanningRequest.model_validate(request_data)
            context = ExecutionContext(
                subject_id=subject_id,
                request_id=f"{run_id}:{case_id}",
                curriculum_snapshot_id=request.curriculumSnapshotId,
                offering_snapshot_id=request.offeringSnapshotId,
                model_id=settings.model_id,
                temperature=settings.temperature,
                deadline=datetime.now(UTC) + timedelta(milliseconds=settings.deadline_ms),
                harness_version=app.state.harness.version,
            )
            answer = app.state.runner.run(request, context)
            records.append(
                {
                    "caseId": case_id,
                    "executionStatus": "COMPLETED",
                    "durationMs": round((time.monotonic() - started) * 1000, 3),
                    "decision": answer.decision,
                    "unknownCodes": sorted(issue.code for issue in answer.unknowns),
                    "recommendationCount": len(answer.recommendations),
                    "usage": answer.usage.model_dump(mode="json"),
                }
            )
        except Exception as exc:  # noqa: BLE001 — failures are evidence and must remain visible
            records.append(
                {
                    "caseId": case_id,
                    "executionStatus": "FAILED",
                    "durationMs": round((time.monotonic() - started) * 1000, 3),
                    "failureType": type(exc).__name__,
                    "usage": None,
                }
            )

    return {
        "reportType": "REAL_MODEL_BASELINE_CAPTURE_NOT_QUALITY_EVALUATION",
        "runId": run_id,
        "createdAt": datetime.now(UTC).isoformat(),
        "manifest": manifest.model_dump(mode="json"),
        "model": {"modelId": settings.model_id, "temperature": settings.temperature},
        "provenance": "SYNTHETIC_FICTION",
        "assessmentStatus": "NOT_ASSESSED_NO_HUMAN_LABELS",
        "limitations": [
            "合成 smoke 输入只用于采集生产 Runner 的模型调用接线、成功/失败与延迟。",
            "无人工真值，不计算正确率，不用于候选晋级；工具与核验结果仍以真实 Java 服务为准。",
            "Provider 未返回的 Token 用量保持 null；失败运行保留在报告中。",
        ],
        "cases": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, required=True, help="报告 JSON 输出路径")
    parser.add_argument("--env-file", type=Path, help="显式指定 CP_ 配置文件，例如 data/private/stack.env")
    parser.add_argument("--subject-id", default=DEFAULT_SUBJECT_ID, help="Java 演示记录主体 ID（默认 S001）")
    parser.add_argument(
        "--curriculum-snapshot-id",
        default=DEFAULT_CURRICULUM_SNAPSHOT_ID,
        help="Java 演示培养方案快照 ID（默认 PLAN_CS_2025）",
    )
    args = parser.parse_args(argv)
    try:
        cases = load_synthetic_cases(args.cases)
        settings = load_settings(args.env_file)
        report = run_baseline(
            cases,
            settings=settings,
            enabled=os.environ.get("CP_BENCHMARK_ENABLE_REAL_MODEL"),
            subject_id=args.subject_id,
            curriculum_snapshot_id=args.curriculum_snapshot_id,
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(case["executionStatus"] == "COMPLETED" for case in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
