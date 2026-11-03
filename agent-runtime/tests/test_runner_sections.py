"""Runner-level section assignment with fake Java tools (docs/36 planning step)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import FACTS_MESSAGE_PREFIX, ModelReply
from agent_runtime.api.schemas import (
    Constraint,
    CourseOffering,
    Issue,
    Meeting,
    PlanItem,
    PlanningRequest,
    TeacherCourseOption,
    TeacherPreference,
)
from agent_runtime.application.budget import Budget
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.runner import PlanningRunner, _dedupe_issues
from agent_runtime.domain.policies.candidate_guard import CourseFact

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

    def __init__(self, offerings: list[CourseOffering], *, extra_rows: int = 0) -> None:
        self._offerings = offerings
        # Other courses in the snapshot. With 100 or more rows the unfiltered page is
        # full, which the runner must treat as "not the whole snapshot".
        self._extra_rows = extra_rows
        self.calls: list[str] = []
        self.offering_lookups: list[str] = []
        self.scans = 0
        self.validation_items: list[PlanItem] | None = None

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        self.calls.append(tool)
        if tool == "listOfferings":
            assert params is not None
            code = params.get("courseCode")
            if code is None:
                self.scans += 1
                rows = list(self._offerings) + [
                    _row(f"FILL{index:03d}", f"class:fill-{index:03d}")
                    for index in range(self._extra_rows)
                ]
                return rows[: params["limit"]]
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
    # A full unfiltered page (100 rows): offered courses are known, but the rows for
    # section assignment still need one listOfferings call per course.
    tools = _OfferingTools(rows, extra_rows=200)
    answer = _run(_request(planning_request), tools, _cs101_math201_items())

    assert tools.offering_lookups == ["CS101", "MATH201"]
    # usage.toolCalls counts only the six-call run budget; offering and review
    # lookups have their own caps and are not in it.
    non_offering = [call for call in tools.calls if call not in {"listOfferings", "searchReviews"}]
    assert answer.usage.toolCalls == len(non_offering)
    assert answer.usage.toolCalls <= 6


def test_offering_cap_leaves_extra_courses_empty_with_reason(
    planning_request: PlanningRequest,
) -> None:
    rows = [
        _row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)]),
        _row("MATH201", "class:math-b", meetings=[_meeting(3, 5, 6)]),
    ]
    tools = _OfferingTools(rows, extra_rows=200)
    # One call for the unfiltered page, one for CS101; MATH201 hits the total cap.
    answer = _run(
        _request(planning_request),
        tools,
        _cs101_math201_items(),
        budget=Budget(max_offering_calls=2),
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


class _CapturingModel:
    """Records the facts payload the model would see, then returns the given items."""

    def __init__(self, items: list[PlanItem]) -> None:
        self._items = items
        self.facts: dict | None = None

    def generate(self, *, context, messages, tool_schemas):
        del context, tool_schemas
        for message in messages:
            content = message.get("content", "")
            if content.startswith(FACTS_MESSAGE_PREFIX):
                self.facts = json.loads(content[len(FACTS_MESSAGE_PREFIX) :])
        return ModelReply(items=list(self._items))


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


def _run_with_model(request: PlanningRequest, tools: _OfferingTools, model) -> object:
    runner = PlanningRunner(
        tool_client=tools,
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=model,
    )
    return runner.run(request, _context(request))


def _unknown_codes(answer) -> list[tuple[str, str]]:
    return [(u.code, u.message) for u in answer.unknowns]


def test_model_pick_that_is_not_offered_is_not_recommended(
    planning_request: PlanningRequest,
) -> None:
    # Only CS101 is offered this term. The model still names MATH201.
    tools = _OfferingTools([_row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)])])
    answer = _run(_request(planning_request), tools, _cs101_math201_items())

    assert [item.courseCode for item in answer.recommendations[0].items] == ["CS101"]
    assert tools.validation_items is not None
    assert [item.courseCode for item in tools.validation_items] == ["CS101"]
    dropped = [u for u in answer.unknowns if u.code == "NOT_OFFERED_DROPPED"]
    assert dropped and "MATH201" in dropped[0].message
    assert "本学期没有开设这门课" in dropped[0].message


def test_pinned_course_not_offered_is_kept_and_stated_from_java_facts(
    planning_request: PlanningRequest,
) -> None:
    tools = _OfferingTools([_row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)])])
    request = _request(planning_request)
    request.intent.hardConstraints = [_pin("MATH201")]
    model = _CapturingModel([PlanItem(courseCode="CS101", teacherKey=None, classId=None)])
    answer = _run_with_model(request, tools, model)

    recommendation = answer.recommendations[0]
    assert [item.courseCode for item in recommendation.items] == ["MATH201", "CS101"]
    assert _class_by_course(answer)["MATH201"] is None
    reason = [u for u in answer.unknowns if u.code == "SECTION_NOT_ASSIGNED"]
    assert reason and reason[0].message == "课程 MATH201：本学期没有开设这门课"
    rationale = {r.courseCode: r for r in recommendation.courseRationales}
    assert "本学期没有开设这门课" in rationale["MATH201"].reason
    assert rationale["MATH201"].rationaleSource == "COURSE_FACTS"
    # The model never saw the unoffered pin, so it is not in the candidate payload.
    assert "MATH201" not in model.facts["courseCodes"]


def test_pinned_offered_course_goes_first_and_model_picks_follow(
    planning_request: PlanningRequest,
) -> None:
    tools = _OfferingTools(
        [
            _row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)]),
            _row("MATH201", "class:math-b", meetings=[_meeting(3, 5, 6)]),
        ]
    )
    request = _request(planning_request)
    request.intent.hardConstraints = [_pin("MATH201")]
    model = _CapturingModel([PlanItem(courseCode="CS101", teacherKey=None, classId=None)])
    answer = _run_with_model(request, tools, model)

    assert [item.courseCode for item in answer.recommendations[0].items] == ["MATH201", "CS101"]
    assert _class_by_course(answer) == {"MATH201": "class:math-b", "CS101": "class:cs101-a"}


def test_payload_marks_offered_and_requirement_nature(planning_request: PlanningRequest) -> None:
    tools = _OfferingTools([_row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)])])
    model = _CapturingModel(
        [
            PlanItem(courseCode="CS101", teacherKey=None, classId=None),
        ]
    )
    _run_with_model(_request(planning_request), tools, model)

    assert model.facts is not None
    assert model.facts["courseCodes"] == ["CS101"]
    course = model.facts["courses"][0]
    assert course["courseCode"] == "CS101"
    assert course["offeredThisTerm"] is True
    assert course["sectionCount"] == 1
    # CS101 is 专业选修课 in the fixture catalog, so the nature is 选修.
    assert course["requirementNature"] == "选修"
    assert course["schoolGapRemainingCredits"] is None


def test_snapshot_without_offering_rows_for_candidates_recommends_nothing(
    planning_request: PlanningRequest,
) -> None:
    tools = _OfferingTools([_row("OTHER", "class:other", meetings=[_meeting(1, 1, 2)])])
    answer = _run(_request(planning_request), tools, _cs101_math201_items())

    # Both picks are dropped (neither is offered), so nothing is recommended.
    assert not answer.recommendations
    dropped = {u.message for u in answer.unknowns if u.code == "NOT_OFFERED_DROPPED"}
    assert dropped == {
        "课程 CS101 本学期没有开设这门课，未纳入推荐",
        "课程 MATH201 本学期没有开设这门课，未纳入推荐",
    }


def test_precheck_budget_spent_leaves_courses_unrecommended_and_says_so(
    planning_request: PlanningRequest,
) -> None:
    # The unfiltered page is full, and CS101 is the only course on it. MATH201 cannot
    # be checked because the precheck budget (scan only) is spent.
    tools = _OfferingTools(
        [_row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)])], extra_rows=200
    )
    answer = _run(
        _request(planning_request),
        tools,
        _cs101_math201_items(),
        budget=Budget(max_offering_precheck_calls=1),
    )

    assert [item.courseCode for item in answer.recommendations[0].items] == ["CS101"]
    checked = [u for u in answer.unknowns if u.code == "OFFERING_NOT_CHECKED"]
    assert checked and "1 门" in checked[0].message
    assert "不代表它们本学期没有开设" in checked[0].message


def test_duplicate_unknowns_are_reported_once() -> None:
    first = Issue(code="TIME_RULE", message="时间类条件未核验", field=None, retryable=False)
    same = Issue(code="TIME_RULE", message="时间类条件未核验", field=None, retryable=False)
    other = Issue(code="TIME_RULE", message="另一条", field=None, retryable=False)
    assert _dedupe_issues([first, same, other]) == [first, other]


def test_fallback_reason_never_calls_a_required_course_elective() -> None:
    fact = CourseFact(
        course_code="08305014",
        name="数据库原理",
        credits="3.00",
        category="学科基础课",
        requirement_nature="必修",
        offered_this_term=False,
        school_gap_credits="3",
    )
    text = PlanningRunner._fallback_reason(fact)
    assert "（专业必修课）" in text
    assert "选修" not in text
    assert "本学期没有开设这门课" in text
    assert "学校报告中「学科基础课」仍差 3 学分" in text


def test_rationale_for_a_dropped_pick_does_not_fail_the_run(
    planning_request: PlanningRequest,
) -> None:
    from agent_runtime.api.schemas.answer import CourseRationale

    class _RationaleModel:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            return ModelReply(
                items=[
                    PlanItem(courseCode="CS101", teacherKey=None, classId=None),
                    PlanItem(courseCode="MATH201", teacherKey=None, classId=None),
                ],
                course_rationales=[
                    CourseRationale(courseCode="CS101", reason="可以选。", reviewNoteIds=[]),
                    CourseRationale(courseCode="MATH201", reason="也可以。", reviewNoteIds=[]),
                ],
            )

    tools = _OfferingTools([_row("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)])])
    answer = _run_with_model(_request(planning_request), tools, _RationaleModel())

    recommendation = answer.recommendations[0]
    assert [item.courseCode for item in recommendation.items] == ["CS101"]
    assert [r.courseCode for r in recommendation.courseRationales] == ["CS101"]


# --- docs/38 planner rules: required first, leaf gaps, taken status (fake Java) ---


def _catalog_course(code: str, name: str, category: str):
    from decimal import Decimal

    from agent_runtime.api.schemas import Course

    return Course(
        courseCode=code,
        name=name,
        credits=Decimal("3"),
        category=category,
        sourceRefIds=["source:fake-w2"],
    )


class _CatalogTools(_OfferingTools):
    """Adds catalog courses and, optionally, a school report built from fixture rows."""

    def __init__(
        self,
        offerings: list[CourseOffering],
        *,
        extra_courses=(),
        school_nodes=None,
        school_courses=None,
        school_record_id: str | None = None,
    ) -> None:
        super().__init__(offerings)
        self._extra_courses = list(extra_courses)
        self._school_nodes = school_nodes
        self._school_courses = school_courses or []
        self._school_record_id = school_record_id

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        if tool == "listCourses":
            base = super().call(tool, dto, context, params=params)
            return [*base, *self._extra_courses]
        if tool == "getSchoolProgress" and self._school_nodes is not None:
            return _school_result(
                self._school_nodes,
                self._school_courses,
                record_id=self._school_record_id,
                record=super().call(
                    "getAcademicRecord", None, context, params={"recordId": "record:demo"}
                ),
            )
        return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)


def _json_number(value):
    """Credits as Java writes them: 1 for "1", not 1.0."""
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _school_result(nodes, courses, *, record_id, record):
    from agent_runtime.api.schemas import SchoolProgressImportResult

    now = datetime.now(UTC).isoformat()
    node_rows = [
        {
            "nodeId": node_id,
            "parentId": parent,
            "schoolNodeId": None,
            "leaf": leaf,
            "name": name,
            "requiredCredits": None,
            "earnedCredits": None,
            "remainingCredits": _json_number(remaining),
        }
        for node_id, parent, name, remaining, leaf in nodes
    ]
    course_rows = [
        {
            "nodeId": node_id,
            "courseCode": code,
            "name": code,
            "credits": 3,
            "outcome": outcome,
            "completedYear": None,
            "completedTerm": None,
            "grade": None,
            "makeup": None,
            "retake": None,
            "suggestedYear": None,
            "suggestedTerm": None,
        }
        for node_id, code, outcome in courses
    ]
    record_dump = record.model_dump(mode="json")
    if record_id is not None:
        record_dump["academicRecordId"] = record_id
    return SchoolProgressImportResult.model_validate(
        {
            "receipt": {
                "schoolProgressId": "school:demo",
                "contentHash": "d" * 64,
                "importedAt": now,
                "reused": True,
            },
            "snapshot": {
                "format": "coursepilot-shu-academic-progress",
                "version": 1,
                "capturedAt": now,
                "source": "browser adapter",
                "nodes": node_rows,
                "courses": course_rows,
            },
            "academicRecord": record_dump,
        }
    )


def test_offered_required_course_goes_first_with_professional_reason(
    planning_request: PlanningRequest,
) -> None:
    tools = _CatalogTools(
        [
            _row("DB201", "class:db-a", meetings=[_meeting(1, 1, 2)]),
            _row("CS101", "class:cs101-a", meetings=[_meeting(2, 3, 4)]),
        ],
        extra_courses=[_catalog_course("DB201", "数据库原理", "学科基础课")],
    )
    model = _CapturingModel([PlanItem(courseCode="CS101", teacherKey=None, classId=None)])
    answer = _run_with_model(_request(planning_request), tools, model)

    plan = answer.recommendations[0]
    assert [item.courseCode for item in plan.items] == ["DB201", "CS101"]
    assert _class_by_course(answer) == {"DB201": "class:db-a", "CS101": "class:cs101-a"}
    rationale = {item.courseCode: item for item in plan.courseRationales}
    assert "专业必修课" in rationale["DB201"].reason
    assert rationale["DB201"].rationaleSource == "COURSE_FACTS"


def test_required_course_blocked_by_hard_time_constraint_is_not_placed(
    planning_request: PlanningRequest,
) -> None:
    tools = _CatalogTools(
        [
            _row("DB201", "class:db-a", meetings=[_meeting(1, 1, 2)]),
            _row("CS101", "class:cs101-a", meetings=[_meeting(2, 3, 4)]),
        ],
        extra_courses=[_catalog_course("DB201", "数据库原理", "学科基础课")],
    )
    request = _request(planning_request)
    request.intent.hardConstraints = [
        Constraint(
            kind="BLOCK_DAY",
            courseCode=None,
            teacherKey=None,
            dayOfWeek=1,
            section=None,
            value=None,
            sourceText="周一不排课",
        )
    ]
    answer = _run_with_model(
        request,
        tools,
        _CapturingModel([PlanItem(courseCode="CS101", teacherKey=None, classId=None)]),
    )

    assert [item.courseCode for item in answer.recommendations[0].items] == ["CS101"]
    codes = [issue.code for issue in answer.unknowns]
    assert "REQUIRED_NOT_PLACED" in codes
    message = next(i.message for i in answer.unknowns if i.code == "REQUIRED_NOT_PLACED")
    assert "DB201" in message


def test_required_course_not_offered_is_named_and_not_placed(
    planning_request: PlanningRequest,
) -> None:
    tools = _CatalogTools(
        [_row("CS101", "class:cs101-a", meetings=[_meeting(2, 3, 4)])],
        extra_courses=[_catalog_course("DB201", "数据库原理", "学科基础课")],
    )
    model = _CapturingModel([PlanItem(courseCode="CS101", teacherKey=None, classId=None)])
    answer = _run_with_model(_request(planning_request), tools, model)

    assert [item.courseCode for item in answer.recommendations[0].items] == ["CS101"]
    message = next(i.message for i in answer.unknowns if i.code == "REQUIRED_NOT_OFFERED")
    assert "DB201" in message


def test_school_in_progress_course_is_not_a_candidate_when_record_differs(
    planning_request: PlanningRequest,
) -> None:
    tools = _CatalogTools(
        [
            _row("ALG", "class:alg-a", meetings=[_meeting(1, 1, 2)]),
            _row("MINE", "class:mine-a", meetings=[_meeting(2, 3, 4)]),
        ],
        extra_courses=[
            _catalog_course("ALG", "算法设计与分析A", "专业选修课"),
            _catalog_course("MINE", "数据挖掘导论", "专业选修课"),
        ],
        school_nodes=[("n:root", None, "专业选修课", None, True)],
        school_courses=[("n:root", "ALG", "IN_PROGRESS")],
        school_record_id="record:school-other",
    )
    model = _CapturingModel([PlanItem(courseCode="MINE", teacherKey=None, classId=None)])
    _run_with_model(_request(planning_request), tools, model)

    assert model.facts is not None
    assert "ALG" not in model.facts["courseCodes"]
    assert "MINE" in model.facts["courseCodes"]


def test_school_gap_targets_leaf_sub_category_only(planning_request: PlanningRequest) -> None:
    tools = _CatalogTools(
        [
            _row("MOR101", "class:mor-a", meetings=[_meeting(1, 1, 2)]),
            _row("MATH101", "class:math-a", meetings=[_meeting(2, 3, 4)]),
            _row("CS101", "class:cs101-a", meetings=[_meeting(3, 5, 6)]),
        ],
        extra_courses=[
            _catalog_course("MOR101", "思想道德与法治", "公共基础课"),
            _catalog_course("MATH101", "高等数学", "公共基础课"),
        ],
        school_nodes=[
            ("n:pub", None, "公共基础课", "1", False),
            ("n:ideo", "n:pub", "思想政治必修课", "1", True),
            ("n:sport", "n:pub", "体育", "0", True),
        ],
        school_courses=[("n:ideo", "MOR101", "NOT_TAKEN"), ("n:sport", "MATH101", "PASSED")],
        school_record_id=None,
    )
    model = _CapturingModel([PlanItem(courseCode="CS101", teacherKey=None, classId=None)])
    _run_with_model(_request(planning_request), tools, model)

    assert model.facts is not None
    assert model.facts["schoolReportGaps"] == [
        {"category": "思想政治必修课", "remainingCredits": "1"}
    ]
    assert "MOR101" in model.facts["courseCodes"]
    assert "MATH101" not in model.facts["courseCodes"]
    course = next(c for c in model.facts["courses"] if c["courseCode"] == "MOR101")
    assert course["schoolGapRemainingCredits"] == "1"
