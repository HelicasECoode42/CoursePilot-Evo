from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.tool_client import ToolClient, ToolUnavailable
from agent_runtime.api.schemas import AuditResult, PlanningRequest
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.runner import PlanningRunner


class FakeToolClient:
    """Test double: returns a minimal (clearly-fake) audit; nothing else."""

    def call(self, tool: str, dto, context):
        if tool == "auditRequirements":
            return AuditResult(
                curriculumSnapshotId=dto.curriculumSnapshotId,
                academicRecordId=dto.academicRecordId,
                recordRevision=1,
                transcriptComplete=False,
                requirements=[],
                suggestedCourseCodes=[],
                unknowns=[],
            )
        raise ToolUnavailable(tool)


def _context(request: PlanningRequest) -> ExecutionContext:
    return ExecutionContext(
        subject_id="subject:demo",
        request_id="req:demo",
        curriculum_snapshot_id=request.curriculumSnapshotId,
        offering_snapshot_id=request.offeringSnapshotId,
        model_id="DEPLOYMENT_MODEL_PLACEHOLDER",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=45),
        harness_version="harness:v0",
    )


def _runner() -> PlanningRunner:
    harness = HarnessSnapshot(version="harness:v0", root=Path("."))
    return PlanningRunner(tool_client=FakeToolClient(), harness=harness)


def test_run_returns_clarify_when_goal_missing(planning_request: PlanningRequest) -> None:
    planning_request.intent.motives = []
    planning_request.intent.hardConstraints = []
    planning_request.intent.pinnedTeacherCoursePairs = []
    planning_request.intent.priorityOrder = []
    answer = _runner().run(planning_request, _context(planning_request))
    assert answer.decision == "CLARIFY"
    assert answer.clarification is not None
    assert answer.recommendations == []
    assert answer.usage.toolCalls == 1
    assert answer.traceId.startswith("trace:")


def test_run_returns_unable_to_verify_when_goal_present(
    planning_request: PlanningRequest,
) -> None:
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    answer = _runner().run(planning_request, _context(planning_request))
    assert answer.decision == "UNABLE_TO_VERIFY"
    assert any(issue.code == "PLANNING_LOOP_PENDING" for issue in answer.unknowns)


def test_run_raises_tool_unavailable_without_java(planning_request: PlanningRequest) -> None:
    harness = HarnessSnapshot(version="harness:v0", root=Path("."))
    runner = PlanningRunner(tool_client=ToolClient(base_url=None, service_key=""), harness=harness)
    with pytest.raises(ToolUnavailable):
        runner.run(planning_request, _context(planning_request))
