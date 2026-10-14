from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import FakeModelAdapter, ModelInvalidOutput, ModelReply
from agent_runtime.adapters.tool_client import ToolClient, ToolUnavailable
from agent_runtime.api.schemas import PlanItem, PlanningRequest
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.runner import PlanningRunner


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


def _runner(model=None) -> PlanningRunner:
    harness = HarnessSnapshot(version="harness:v0", root=Path("."))
    return PlanningRunner(
        tool_client=TypedFakeToolClient(),
        harness=harness,
        model_adapter=model or FakeModelAdapter(),
    )


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


def test_run_returns_course_layer_recommendations_on_w2_fake_loop(
    planning_request: PlanningRequest,
) -> None:
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    answer = _runner().run(planning_request, _context(planning_request))
    assert answer.decision == "RECOMMENDATIONS"
    assert len(answer.recommendations) == 1
    recommendation = answer.recommendations[0]
    assert recommendation.verification.verdict == "UNKNOWN"
    assert recommendation.verification.scope == "COURSE_ONLY"
    assert {item.courseCode for item in recommendation.items} <= {"CS101", "MATH201"}
    assert any(issue.code == "OFFERING_UNAVAILABLE" for issue in answer.unknowns)
    assert any(issue.code == "FAKE_TOOL" for issue in answer.unknowns)


def test_run_rejects_invented_course_ids(planning_request: PlanningRequest) -> None:
    class InventingModel:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            return ModelReply(items=[PlanItem(courseCode="CS999", teacherKey=None, classId=None)])

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    answer = _runner(InventingModel()).run(planning_request, _context(planning_request))
    assert answer.decision == "UNABLE_TO_VERIFY"
    assert any(issue.code == "UNKNOWN_COURSE" for issue in answer.unknowns)


def test_run_stops_after_one_invalid_output_repair(planning_request: PlanningRequest) -> None:
    class AlwaysInvalid:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            raise ModelInvalidOutput("broken json")

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    answer = _runner(AlwaysInvalid()).run(planning_request, _context(planning_request))
    assert answer.decision == "UNABLE_TO_VERIFY"
    assert any(issue.code == "MODEL_INVALID_OUTPUT" for issue in answer.unknowns)


def test_run_raises_tool_unavailable_without_java(planning_request: PlanningRequest) -> None:
    harness = HarnessSnapshot(version="harness:v0", root=Path("."))
    runner = PlanningRunner(tool_client=ToolClient(base_url=None, service_key=""), harness=harness)
    with pytest.raises(ToolUnavailable):
        runner.run(planning_request, _context(planning_request))
