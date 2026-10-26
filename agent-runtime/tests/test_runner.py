from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import (
    FakeModelAdapter,
    ModelInvalidOutput,
    ModelReply,
    ModelTimeout,
)
from agent_runtime.adapters.result_repository import FileResultRepository
from agent_runtime.adapters.tool_client import ToolClient, ToolUnavailable
from agent_runtime.api.schemas import (
    AuditResult,
    Constraint,
    Course,
    PlanItem,
    PlanningRequest,
    PlanValidation,
    RunManifest,
    TeacherPreference,
)
from agent_runtime.application.budget import Budget, BudgetExceeded
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
    assert any(issue.code == "FAKE_MODEL" for issue in answer.unknowns)
    assert all(issue.code != "FAKE_MODEL" for issue in recommendation.verification.unknownChecks)


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


def test_run_does_not_retry_invalid_model_output(planning_request: PlanningRequest) -> None:
    class AlwaysInvalid:
        calls = 0

        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            type(self).calls += 1
            raise ModelInvalidOutput("broken json")

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    with pytest.raises(ModelInvalidOutput):
        _runner(AlwaysInvalid()).run(planning_request, _context(planning_request))
    assert AlwaysInvalid.calls == 1


def test_run_charges_tokens_of_invalid_model_output(planning_request: PlanningRequest) -> None:
    class InvalidWithUsage:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            error = ModelInvalidOutput("broken json")
            error.input_tokens = 7
            error.output_tokens = 3
            raise error

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    runner = PlanningRunner(
        tool_client=TypedFakeToolClient(),
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=InvalidWithUsage(),
        budget=Budget(max_input_tokens=5),
    )
    # The failed call's 7 input tokens exceed the 5-token cap, so the budget error wins
    # over the invalid-output error: the tokens were charged, not silently dropped.
    with pytest.raises(BudgetExceeded):
        runner.run(planning_request, _context(planning_request))


def test_run_does_not_repair_model_timeout(planning_request: PlanningRequest) -> None:
    class TimedOut:
        calls = 0

        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            type(self).calls += 1
            raise ModelTimeout("模型请求超时")

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    with pytest.raises(ModelTimeout):
        _runner(TimedOut()).run(planning_request, _context(planning_request))
    assert TimedOut.calls == 1


def test_run_records_provider_token_usage(planning_request: PlanningRequest) -> None:
    class CountingModel:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            return ModelReply(
                items=[PlanItem(courseCode="CS101", teacherKey=None, classId=None)],
                input_tokens=12,
                output_tokens=4,
            )

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    answer = _runner(CountingModel()).run(planning_request, _context(planning_request))
    assert answer.usage.inputTokens == 12
    assert answer.usage.outputTokens == 4


def test_run_persists_sanitized_trace_and_manifest(
    planning_request: PlanningRequest, tmp_path: Path
) -> None:
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    repository = FileResultRepository(tmp_path)
    runner = PlanningRunner(
        tool_client=TypedFakeToolClient(),
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        result_repository=repository,
    )
    answer = runner.run(planning_request, _context(planning_request))
    directory = tmp_path / answer.traceId.replace(":", "_")
    events = [
        line
        for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert events
    last_event = json.loads(events[-1])
    assert last_event["eventType"] == "FINAL_DELIVERED"
    assert last_event["inputTokens"] is None
    assert last_event["outputTokens"] is None
    assert "promptText" not in (directory / "events.jsonl").read_text(encoding="utf-8")
    manifest = RunManifest.model_validate_json(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    enforced = Budget()
    assert manifest.maxInputTokens == enforced.max_input_tokens == 8000
    assert manifest.maxOutputTokens == enforced.max_output_tokens == 2000
    assert manifest.maxToolCalls == enforced.max_tool_calls == 6
    assert manifest.maxModelCalls == enforced.max_model_calls == 3
    assert manifest.deadlineMs == enforced.deadline_ms == 45000
    assert manifest.modelId == "DEPLOYMENT_MODEL_PLACEHOLDER"
    saved = json.loads((directory / "answer.json").read_text(encoding="utf-8"))
    assert saved["decision"] == answer.decision


def test_run_clarifies_must_teacher_vs_hard_time(planning_request: PlanningRequest) -> None:
    planning_request.intent.motives = ["SPECIFIC_TEACHER", "SCHEDULE"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.intent.pinnedTeacherCoursePairs = [
        TeacherPreference(courseCode="CS101", teacherKey="teacher:demo", mode="MUST")
    ]
    planning_request.intent.hardConstraints = [
        Constraint(
            kind="BLOCK_SLOT",
            courseCode=None,
            teacherKey=None,
            dayOfWeek=5,
            section=1,
            value=None,
            sourceText="周五第1节必须空",
        )
    ]
    answer = _runner().run(planning_request, _context(planning_request))
    assert answer.decision == "CLARIFY"
    assert answer.clarification is not None
    assert answer.clarification.questionId == "tradeoff:teacher-vs-schedule"
    assert answer.recommendations == []
    assert {choice.value for choice in answer.clarification.choices} == {
        "KEEP_TEACHER",
        "KEEP_SCHEDULE",
    }


def test_empty_candidate_list_is_unable_to_verify(planning_request: PlanningRequest) -> None:
    class EmptyReply:
        calls = 0

        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            type(self).calls += 1
            return ModelReply(items=[])

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    answer = _runner(EmptyReply()).run(planning_request, _context(planning_request))
    assert EmptyReply.calls == 1
    assert answer.decision == "UNABLE_TO_VERIFY"
    assert answer.recommendations == []
    assert any(issue.code == "EVIDENCE_MISMATCH" for issue in answer.unknowns)
    assert all(issue.code != "FAKE_MODEL" for issue in answer.unknowns)


def test_empty_tool_catalog_is_unable_to_verify(planning_request: PlanningRequest) -> None:
    class EmptyCatalog:
        def call(self, tool, dto, context, *, params=None):
            del context, params
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
            if tool in {"listCourses", "listTeacherCourseOptions"}:
                return []
            raise AssertionError(tool)

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    runner = PlanningRunner(
        tool_client=EmptyCatalog(),
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=FakeModelAdapter(),
    )
    answer = runner.run(planning_request, _context(planning_request))
    assert answer.decision == "UNABLE_TO_VERIFY"
    assert answer.recommendations == []
    assert any(issue.code == "EVIDENCE_MISMATCH" for issue in answer.unknowns)
    assert any(issue.code == "FAKE_MODEL" for issue in answer.unknowns)


def test_fake_model_marker_does_not_rewrite_valid_verdict(
    planning_request: PlanningRequest,
) -> None:
    class ValidJava:
        def call(self, tool, dto, context, *, params=None):
            del context, params
            if tool == "auditRequirements":
                return AuditResult(
                    curriculumSnapshotId=dto.curriculumSnapshotId,
                    academicRecordId=dto.academicRecordId,
                    recordRevision=1,
                    transcriptComplete=True,
                    requirements=[],
                    suggestedCourseCodes=["CS101"],
                    unknowns=[],
                )
            if tool == "listCourses":
                return [
                    Course(
                        courseCode="CS101",
                        name="程序设计基础",
                        credits=Decimal("4.00"),
                        category="必修",
                        sourceRefIds=["source:demo"],
                    )
                ]
            if tool == "listTeacherCourseOptions":
                return []
            if tool == "validatePlan":
                return PlanValidation(
                    verifierResultId="verify:demo",
                    verdict="VALID",
                    scope="COURSE_ONLY",
                    curriculumSnapshotId=dto.curriculumSnapshotId,
                    offeringSnapshotId=dto.offeringSnapshotId,
                    recordRevision=1,
                    violations=[],
                    unknownChecks=[],
                    performedChecks=["COURSE_EXISTS"],
                    sourceRefIds=["source:demo"],
                )
            raise AssertionError(tool)

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    runner = PlanningRunner(
        tool_client=ValidJava(),
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=FakeModelAdapter(),
    )
    answer = runner.run(planning_request, _context(planning_request))
    assert answer.decision == "RECOMMENDATIONS"
    verification = answer.recommendations[0].verification
    assert verification.verdict == "VALID"
    assert verification.unknownChecks == []
    assert any(issue.code == "FAKE_MODEL" for issue in answer.unknowns)


def test_configured_model_has_no_fake_marker(planning_request: PlanningRequest) -> None:
    class ConfiguredModel:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            return ModelReply(items=[PlanItem(courseCode="CS101", teacherKey=None, classId=None)])

    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    answer = _runner(ConfiguredModel()).run(planning_request, _context(planning_request))
    assert answer.decision == "RECOMMENDATIONS"
    assert all(issue.code != "FAKE_MODEL" for issue in answer.unknowns)


def test_run_raises_tool_unavailable_without_java(planning_request: PlanningRequest) -> None:
    harness = HarnessSnapshot(version="harness:v0", root=Path("."))
    runner = PlanningRunner(tool_client=ToolClient(base_url=None, service_key=""), harness=harness)
    with pytest.raises(ToolUnavailable):
        runner.run(planning_request, _context(planning_request))
