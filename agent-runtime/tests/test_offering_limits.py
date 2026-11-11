"""listOfferings is read past the first 20 / 100 rows when one course has many sections.

Java's listOfferings has no cursor. For one courseCode it returns up to 1000 rows
(COURSE_OFFERING_LIMIT); without a courseCode it returns at most 100. The fakes below
mirror those caps, including Java's default of 20 when ``limit`` is omitted, so a
caller that forgets to pass ``limit`` fails here instead of silently losing sections.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import ModelReply
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import (
    CourseOffering,
    Meeting,
    PlanItem,
    PlanningRequest,
    TeacherCourseOption,
)
from agent_runtime.api.settings import Settings
from agent_runtime.application.budget import Budget
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.offering_check import COURSE_OFFERING_LIMIT, OFFERING_PAGE_LIMIT
from agent_runtime.application.offering_summary import summarize_offerings
from agent_runtime.application.runner import PlanningRunner

OFFERING_SNAPSHOT = "offering-snapshot:demo"


def _meeting(day: int, start: int, end: int) -> Meeting:
    return Meeting(dayOfWeek=day, sectionStart=start, sectionEnd=end, weeks=list(range(1, 17)))


def _row(course: str, class_id: str, meetings: list[Meeting] | None = None) -> CourseOffering:
    return CourseOffering(
        courseCode=course,
        classId=class_id,
        teacherKey="teacher:a",
        teacherText="演示教师",
        credits=None,
        capacity=None,
        meetingTextRaw="演示",
        meetings=meetings if meetings is not None else [_meeting(1, 1, 2)],
        parseStatus="PARSED",
        sourceRefId="source:demo",
    )


class _JavaOfferings(TypedFakeToolClient):
    """listOfferings with Java's caps: 100 unfiltered (default 20), 1000 per course."""

    def __init__(self, rows: list[CourseOffering], *, extra_rows: int = 0) -> None:
        self._rows = list(rows)
        self._extra_rows = extra_rows
        self.calls: list[str] = []
        self.limits: list[tuple[str | None, int]] = []

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        self.calls.append(tool)
        if tool == "listOfferings":
            assert params is not None
            code = params.get("courseCode")
            cap = OFFERING_PAGE_LIMIT if code is None else COURSE_OFFERING_LIMIT
            limit = params.get("limit", 20)
            self.limits.append((code, limit))
            assert 1 <= limit <= cap, f"Java would reject limit={limit}"
            if code is None:
                pad = [_row(f"FILL{i:03d}", f"class:fill-{i:03d}") for i in range(self._extra_rows)]
                return (self._rows + pad)[:limit]
            return [row for row in self._rows if row.courseCode == code][:limit]
        if tool == "listTeacherCourseOptions":
            return [
                TeacherCourseOption(
                    courseCode=code,
                    teacherKey="teacher:a",
                    teacherDisplayName="甲",
                    availability="UNKNOWN",
                    reviewNoteIds=[],
                    classIds=[],
                )
                for code in ("CS101", "MATH201")
            ]
        return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)


def _many_sections(course: str, count: int) -> list[CourseOffering]:
    return [_row(course, f"class:{course.lower()}-{i:03d}") for i in range(count)]


# ---------------------------------------------------------------- planner (runner)


def _planner_request(planning_request: PlanningRequest) -> PlanningRequest:
    planning_request.offeringSnapshotId = OFFERING_SNAPSHOT
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.intent.hardConstraints = []
    planning_request.intent.softPreferences = []
    planning_request.intent.pinnedTeacherCoursePairs = []
    return planning_request


class _Model:
    def __init__(self, items: list[PlanItem]) -> None:
        self._items = items

    def generate(self, *, context, messages):
        del context, messages
        return ModelReply(items=list(self._items))


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


def test_planner_assigns_a_section_that_sits_beyond_the_first_100_rows(
    planning_request: PlanningRequest,
) -> None:
    # CS101 has 150 sections. MATH201 occupies day 1 periods 1-2, which clashes with
    # the first 149 CS101 sections, so the only usable one is row 150 (index 149).
    cs101 = _many_sections("CS101", 149) + [
        _row("CS101", "class:cs101-free", meetings=[_meeting(2, 3, 4)])
    ]
    math = [_row("MATH201", "class:math-a", meetings=[_meeting(1, 1, 2)])]
    tools = _JavaOfferings(cs101 + math)
    request = _planner_request(planning_request)
    runner = PlanningRunner(
        tool_client=tools,
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=_Model(
            [
                PlanItem(courseCode="CS101", teacherKey=None, classId=None),
                PlanItem(courseCode="MATH201", teacherKey=None, classId=None),
            ]
        ),
        budget=Budget(),
    )
    answer = runner.run(request, _context(request))

    picked = {item.courseCode: item.classId for item in answer.recommendations[0].items}
    assert picked["CS101"] == "class:cs101-free"
    # The per-course lookup asked Java for the course limit, not the default 20 or 100.
    assert ("CS101", COURSE_OFFERING_LIMIT) in tools.limits


# ---------------------------------------------------------------- section counts (offering-summary)


def _summary(tools: _JavaOfferings, codes: list[str]):
    context = ExecutionContext(
        subject_id="subject:demo",
        request_id="req:demo",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id="offer:demo",
        model_id="none",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=30),
        harness_version="harness:v0",
    )
    return summarize_offerings(
        tools,
        context,
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id="offer:demo",
        course_codes=codes,
    )


def test_summary_counts_all_186_sections_of_one_course() -> None:
    # A full unfiltered page forces the per-course path, which is where the cap applied.
    tools = _JavaOfferings(
        _many_sections("CS101", 186) + _many_sections("MATH201", 106), extra_rows=200
    )
    summary = _summary(tools, ["CS101", "MATH201"])

    counts = {item.courseCode: item.sectionCount for item in summary.items}
    assert counts == {"CS101": 186, "MATH201": 106}
    assert summary.unknown_course_codes == []


def test_summary_marks_a_course_at_the_ceiling_as_unknown_not_complete() -> None:
    tools = _JavaOfferings(_many_sections("CS101", COURSE_OFFERING_LIMIT), extra_rows=200)
    summary = _summary(tools, ["CS101"])

    assert summary.unknown_course_codes == ["CS101"]
    assert summary.items == []


# ---------------------------------------------------------------- session offerings


def _replacement_app(tools) -> TestClient:
    return TestClient(create_app(Settings(), tool_client=tools))


def test_session_offerings_lists_every_section_of_a_course() -> None:
    tools = _JavaOfferings(_many_sections("CS101", 186))
    client = _replacement_app(tools)
    data = client.post("/api/v1/sessions").json()["data"]
    session_id, token = data["sessionId"], data["sessionToken"]
    client.app.state.plan_store.remember(
        session_id=session_id,
        plan_id="plan:plain",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id="offer:demo",
        academic_record_id="record:demo",
        mode="REAL",
        items=[PlanItem(courseCode="CS101", teacherKey=None, classId=None)],
        hard_constraints=[],
        verifier_result_id="verify:plain",
    )

    response = client.get(
        "/api/v1/session-offerings",
        params={"previousPlanId": "plan:plain", "courseCode": "CS101"},
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": "req:limits"},
    )

    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) == 186
    assert ("CS101", COURSE_OFFERING_LIMIT) in tools.limits
