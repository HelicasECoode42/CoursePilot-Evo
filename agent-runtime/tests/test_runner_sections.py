"""Runner-level section assignment with fake Java tools (docs/36 planning step)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import ModelReply
from agent_runtime.api.schemas import (
    CourseOffering,
    Meeting,
    PlanItem,
    PlanningRequest,
    TeacherCourseOption,
    TeacherPreference,
)
from agent_runtime.application.budget import Budget
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.runner import PlanningRunner

OFFERING_SNAPSHOT = "offering-snapshot:demo"


def _meeting(day: int, start: int, end: int) -> Meeting:
    return Meeting(dayOfWeek=day, sectionStart=start, sectionEnd=end, weeks=list(range(1, 17)))


def _row(
    course: str,
    class_id: str,
    *,
    teacher: str | None = "teacher:a",
    meetings: list[Meeting] | None = None,
    parse: str = "PARSED",
) -> CourseOffering:
    return CourseOffering(
        courseCode=course,
        classId=class_id,
        teacherKey=teacher,
        teacherText="演示教师",
        credits=None,
        capacity=None,
        meetingTextRaw="演示",
        meetings=meetings if meetings is not None else [_meeting(1, 1, 2)],
        parseStatus=parse,
        sourceRefId="source:demo",
    )


class _OfferingTools(TypedFakeToolClient):
    """Fake Java: fixed courses, teacher options and offerings; records every call."""

    _TEACHERS = (
        TeacherCourseOption(
            courseCode="CS101",
            teacherKey="teacher:a",
            teacherDisplayName="甲",
            availability="UNKNOWN",
            reviewNoteIds=[],
            classIds=[],
        ),
        TeacherCourseOption(
            courseCode="CS101",
            teacherKey="teacher:b",
            teacherDisplayName="乙",
            availability="UNKNOWN",
            reviewNoteIds=[],
            classIds=[],
        ),
        TeacherCourseOption(
            courseCode="MATH201",
            teacherKey="teacher:a",
            teacherDisplayName="甲",
            availability="UNKNOWN",
            reviewNoteIds=[],
            classIds=[],
        ),
    )

    def __init__(self, offerings: list[CourseOffering]) -> None:
        self._offerings = offerings
        self.calls: list[str] = []
        self.offering_lookups: list[str] = []
        self.validation_items: list[PlanItem] | None = None

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        self.calls.append(tool)
        if tool == "listOfferings":
            assert params is not None
            code = params["courseCode"]
            self.offering_lookups.append(code)
            return [row for row in self._offerings if row.courseCode == code]
        if tool == "listTeacherCourseOptions":
            return list(self._TEACHERS)
        if tool == "validatePlan":
            self.validation_items = list(dto.items)
        return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)


class _Model:
    def __init__(self, items: list[PlanItem]) -> None:
        self._items = items

    def generate(self, *, context, messages, tool_schemas):
        del context, messages, tool_schemas
        return ModelReply(items=list(self._items))


def _request(
    planning_request: PlanningRequest,
    *,
    must: dict[str, str] | None = None,
) -> PlanningRequest:
    planning_request.offeringSnapshotId = OFFERING_SNAPSHOT
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.intent.hardConstraints = []
    planning_request.intent.softPreferences = []
    planning_request.intent.pinnedTeacherCoursePairs = [
        TeacherPreference(courseCode=code, teacherKey=teacher, mode="MUST")
        for code, teacher in (must or {}).items()
    ]
    return planning_request


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


def _run(
    request: PlanningRequest,
    tools: _OfferingTools,
    items: list[PlanItem],
    budget: Budget | None = None,
):
    runner = PlanningRunner(
        tool_client=tools,
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=_Model(items),
        budget=budget,
    )
    return runner.run(request, _context(request))


def _cs101_math201_items() -> list[PlanItem]:
    return [
        PlanItem(courseCode="CS101", teacherKey=None, classId=None),
        PlanItem(courseCode="MATH201", teacherKey=None, classId=None),
    ]


def _class_by_course(answer) -> dict[str, str | None]:
    return {item.courseCode: item.classId for item in answer.recommendations[0].items}


def test_assigns_conflict_free_sections_and_sends_them_to_validation(
    planning_request: PlanningRequest,
) -> None:
    rows = [
        _row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)]),
        _row("CS101", "class:cs101-b", meetings=[_meeting(2, 3, 4)]),
        _row("MATH201", "class:math-a", meetings=[_meeting(1, 1, 2)]),
        _row("MATH201", "class:math-b", meetings=[_meeting(3, 5, 6)]),
    ]
    tools = _OfferingTools(rows)
    answer = _run(_request(planning_request), tools, _cs101_math201_items())

    assert _class_by_course(answer) == {"CS101": "class:cs101-a", "MATH201": "class:math-b"}
    assert {item.courseCode: item.classId for item in tools.validation_items} == {
        "CS101": "class:cs101-a",
        "MATH201": "class:math-b",
    }
    assert not [u for u in answer.unknowns if u.code == "SECTION_NOT_ASSIGNED"]


def test_one_lookup_per_course_and_tool_budget_unchanged(
    planning_request: PlanningRequest,
) -> None:
    rows = [
        _row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)]),
        _row("MATH201", "class:math-b", meetings=[_meeting(3, 5, 6)]),
    ]
    tools = _OfferingTools(rows)
    answer = _run(_request(planning_request), tools, _cs101_math201_items())

    assert tools.offering_lookups == ["CS101", "MATH201"]
    # usage.toolCalls counts only the six-call run budget; lookups are not in it.
    non_offering = [call for call in tools.calls if call != "listOfferings"]
    assert answer.usage.toolCalls == len(non_offering)
    assert answer.usage.toolCalls <= 6


def test_offering_cap_leaves_extra_courses_empty_with_reason(
    planning_request: PlanningRequest,
) -> None:
    rows = [
        _row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)]),
        _row("MATH201", "class:math-b", meetings=[_meeting(3, 5, 6)]),
    ]
    tools = _OfferingTools(rows)
    answer = _run(
        _request(planning_request),
        tools,
        _cs101_math201_items(),
        budget=Budget(max_offering_calls=1),
    )

    assert tools.offering_lookups == ["CS101"]
    assert _class_by_course(answer) == {"CS101": "class:cs101-a", "MATH201": None}
    reasons = [u for u in answer.unknowns if u.code == "SECTION_NOT_ASSIGNED"]
    assert len(reasons) == 1
    assert reasons[0].field == "items[1].classId"
    assert "次数已达上限" in reasons[0].message


def test_must_teacher_pin_decides_the_section(planning_request: PlanningRequest) -> None:
    rows = [
        _row("CS101", "class:cs101-a", teacher="teacher:a", meetings=[_meeting(1, 1, 2)]),
        _row("CS101", "class:cs101-b", teacher="teacher:b", meetings=[_meeting(2, 3, 4)]),
    ]
    tools = _OfferingTools(rows)
    items = [PlanItem(courseCode="CS101", teacherKey="teacher:b", classId=None)]
    answer = _run(
        _request(planning_request, must={"CS101": "teacher:b"}),
        tools,
        items,
    )

    assert _class_by_course(answer) == {"CS101": "class:cs101-b"}
    assert tools.validation_items[0].teacherKey == "teacher:b"


def test_parsed_section_beats_unparsed_one(planning_request: PlanningRequest) -> None:
    rows = [
        _row("CS101", "class:cs101-a", parse="UNPARSED", meetings=[]),
        _row("CS101", "class:cs101-b", meetings=[_meeting(2, 1, 2)]),
    ]
    tools = _OfferingTools(rows)
    items = [PlanItem(courseCode="CS101", teacherKey=None, classId=None)]
    answer = _run(_request(planning_request), tools, items)

    assert _class_by_course(answer) == {"CS101": "class:cs101-b"}


def test_only_unparsed_sections_leave_class_empty_with_reason(
    planning_request: PlanningRequest,
) -> None:
    rows = [_row("CS101", "class:cs101-a", parse="UNPARSED", meetings=[])]
    tools = _OfferingTools(rows)
    items = [PlanItem(courseCode="CS101", teacherKey=None, classId=None)]
    answer = _run(_request(planning_request), tools, items)

    assert _class_by_course(answer) == {"CS101": None}
    reasons = [u for u in answer.unknowns if u.code == "SECTION_NOT_ASSIGNED"]
    assert reasons and "未解析" in reasons[0].message


def test_impossible_combination_keeps_one_class_and_explains_the_other(
    planning_request: PlanningRequest,
) -> None:
    rows = [
        _row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)]),
        _row("MATH201", "class:math-a", meetings=[_meeting(1, 2, 3)]),
    ]
    tools = _OfferingTools(rows)
    answer = _run(_request(planning_request), tools, _cs101_math201_items())

    assigned = {k: v for k, v in _class_by_course(answer).items() if v is not None}
    assert assigned == {"CS101": "class:cs101-a"}
    reasons = [u for u in answer.unknowns if u.code == "SECTION_NOT_ASSIGNED"]
    assert len(reasons) == 1
    assert "冲突" in reasons[0].message
    assert tools.validation_items[1].classId is None


def test_without_offering_snapshot_nothing_is_looked_up(
    planning_request: PlanningRequest,
) -> None:
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.intent.hardConstraints = []
    planning_request.intent.softPreferences = []
    planning_request.intent.pinnedTeacherCoursePairs = []
    planning_request.offeringSnapshotId = None
    tools = _OfferingTools([])
    answer = _run(planning_request, tools, _cs101_math201_items())

    assert tools.offering_lookups == []
    assert _class_by_course(answer) == {"CS101": None, "MATH201": None}
