"""Planning reply size: the model writes less, and a long reply is trimmed and reported.

2026-11-03 real run: 127 courses, 1 pinned course, output cap 4000 tokens. The model was
allowed up to 30 recommended courses with 500-character reasons, so the reply was cut off
(finish_reason=length) and reported as MODEL_OUTPUT_TRUNCATED. The reply is now kept
short by the prompt, the parser fills what Java and the runner already know, and the
runner trims extra picks with a visible issue as a backstop.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessLoader, HarnessSnapshot
from agent_runtime.adapters.model_client import (
    FACTS_MESSAGE_PREFIX,
    HttpModelAdapter,
    ModelInvalidOutput,
    ModelOutputTruncated,
    ModelReply,
    _reply_from_content,
)
from agent_runtime.api.schemas import (
    Constraint,
    CourseOffering,
    Meeting,
    PlanItem,
    PlanningRequest,
)
from agent_runtime.api.schemas.answer import CourseRationale
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.runner import PlanningRunner

OFFERING_SNAPSHOT = "offering-snapshot:demo"
REPO_HARNESS = Path(__file__).resolve().parents[1] / "harness"
MANY_CODES = [f"CS{300 + index}" for index in range(12)]


def _row(index: int, code: str) -> CourseOffering:
    # One slot per course (day and period differ), so no two picks conflict.
    day, period = index % 5 + 1, 2 * (index // 5) + 1
    return CourseOffering(
        courseCode=code,
        classId=f"class:{code.lower()}",
        teacherKey=None,
        teacherText="演示教师",
        credits=None,
        capacity=None,
        meetingTextRaw="演示",
        meetings=[
            Meeting(
                dayOfWeek=day,
                sectionStart=period,
                sectionEnd=period + 1,
                weeks=list(range(1, 17)),
            )
        ],
        parseStatus="PARSED",
        sourceRefId="source:demo",
    )


class _ManyCourses(TypedFakeToolClient):
    """Java stand-in: twelve courses, each offered once in its own slot."""

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        if tool == "listCourses":
            template = TypedFakeToolClient._COURSES[0]
            return [template.model_copy(update={"courseCode": code}) for code in MANY_CODES]
        if tool == "listOfferings":
            assert params is not None
            code = params.get("courseCode")
            rows = [_row(index, c) for index, c in enumerate(MANY_CODES)]
            if code is None:
                return rows[: params["limit"]]
            return [row for row in rows if row.courseCode == code]
        if tool == "listTeacherCourseOptions":
            return []
        return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)


def _request(planning_request: PlanningRequest) -> PlanningRequest:
    planning_request.offeringSnapshotId = OFFERING_SNAPSHOT
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.intent.hardConstraints = []
    planning_request.intent.softPreferences = []
    planning_request.intent.pinnedTeacherCoursePairs = []
    return planning_request


def _pin(course_code: str) -> Constraint:
    return Constraint(
        kind="PIN_COURSE",
        courseCode=course_code,
        teacherKey=None,
        dayOfWeek=None,
        section=None,
        value=None,
        sourceText="学生选入规划的课程",
    )


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


class _LongReplyModel:
    """Ignores the length rule: picks every course and writes 500-character reasons."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def generate(self, *, context, messages, tool_schemas):
        del context, tool_schemas
        self.messages = messages
        return ModelReply(
            items=[PlanItem(courseCode=code, teacherKey=None, classId=None) for code in MANY_CODES],
            course_rationales=[
                CourseRationale(courseCode=code, reason="理由" * 250, reviewNoteIds=[])
                for code in MANY_CODES
            ],
        )


def _run(request: PlanningRequest, model) -> object:
    runner = PlanningRunner(
        tool_client=_ManyCourses(),
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=model,
    )
    return runner.run(request, _context(request))


def test_long_reply_is_trimmed_to_the_limit_and_says_so(planning_request: PlanningRequest) -> None:
    request = _request(planning_request)
    answer = _run(request, _LongReplyModel())

    assert answer.decision == "RECOMMENDATIONS"
    recommendation = answer.recommendations[0]
    # Default limit is 8 (harness/context_policy.yaml); the first picks in the model's order stay.
    assert [item.courseCode for item in recommendation.items] == MANY_CODES[:8]
    assert len(recommendation.courseRationales) == 8
    trimmed = [u for u in answer.unknowns if u.code == "RECOMMENDATION_LIMIT_TRIMMED"]
    assert trimmed and "只保留前 8 门" in trimmed[0].message


def test_pinned_course_is_kept_inside_the_limit(planning_request: PlanningRequest) -> None:
    request = _request(planning_request)
    pinned = MANY_CODES[-1]  # last in the model's order: must still come first
    request.intent.hardConstraints = [_pin(pinned)]
    answer = _run(request, _LongReplyModel())

    codes = [item.courseCode for item in answer.recommendations[0].items]
    assert codes[0] == pinned
    assert len(codes) == 8
    assert set(codes) - {pinned} <= set(MANY_CODES[:-1])


def test_model_reply_without_teacher_or_review_keys_is_accepted() -> None:
    """The model writes only courseCode; Java/runner fill the rest."""
    reply = _reply_from_content(
        json.dumps(
            {
                "items": [{"courseCode": "CS101"}],
                "courseRationales": [{"courseCode": "CS101", "reason": "学习基础"}],
                "explorationDirections": [],
            }
        )
    )
    assert reply.items == [PlanItem(courseCode="CS101", teacherKey=None, classId=None)]
    assert reply.course_rationales[0].reviewNoteIds == []
    assert reply.course_rationales[0].reason == "学习基础"


def test_model_reply_with_extra_item_key_is_still_rejected() -> None:
    with pytest.raises(ModelInvalidOutput):
        _reply_from_content(json.dumps({"items": [{"courseCode": "CS101", "credits": 4}]}))


def test_truncated_reply_over_http_is_reported_as_truncation() -> None:
    cut_off = '{"items":[{"courseCode":"CS101","teacherKey":null,"classId":null},{"courseCode":"CS1'

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": cut_off}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 900, "completion_tokens": 4000},
            },
        )

    adapter = HttpModelAdapter(
        "https://model.test/v1",
        "test-key",
        "test-model",
        0.0,
        4000,
        transport=httpx.MockTransport(handler),
    )
    context = ExecutionContext(
        subject_id="subject:demo",
        request_id="req:demo",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id=None,
        model_id="test-model",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=20),
        harness_version="harness:v0",
    )
    with pytest.raises(ModelOutputTruncated) as caught:
        adapter.generate(context=context, messages=[], tool_schemas=[])
    assert caught.value.output_tokens == 4000


def test_prompt_states_the_course_and_reason_limits(planning_request: PlanningRequest) -> None:
    model = _LongReplyModel()
    _run(_request(planning_request), model)
    system = model.messages[0]["content"]
    assert "推荐课程总数最多 8 门" in system
    assert "120 字" in system
    assert "items 每项只写 courseCode" in system
    assert any(message["content"].startswith(FACTS_MESSAGE_PREFIX) for message in model.messages)


def test_repo_harness_sets_the_recommended_course_limit() -> None:
    snapshot = HarnessLoader(REPO_HARNESS).load()
    assert snapshot.context.max_recommended_courses == 8


def test_output_token_budget_is_unchanged_by_this_change() -> None:
    """Shrinking the reply is the fix; the frozen per-run output cap stays at 4000."""
    from agent_runtime.application.budget import Budget, SessionSpendCap

    assert Budget().max_output_tokens == 4000
    assert SessionSpendCap().max_output_tokens == 20000
