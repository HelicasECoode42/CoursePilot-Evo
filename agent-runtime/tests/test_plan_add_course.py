"""Add one course to a saved session plan, then revalidate the whole plan.

The scripted tool stands in for Java. Every refusal here must happen before a
validatePlan call, and a refused add must leave the saved plan unchanged.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.tool_client import ToolUnavailable
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import (
    AcademicRecord,
    CompletedCourse,
    Course,
    CourseOffering,
    Issue,
    Meeting,
    PlanItem,
    PlanValidation,
    SnapshotSummary,
)
from agent_runtime.api.settings import Settings

_CURRICULUM = (
    Course(
        courseCode="CS101",
        name="程序设计基础",
        credits=Decimal("4.00"),
        category="专业必修",
        sourceRefIds=["source:demo"],
    ),
    Course(
        courseCode="MATH201",
        name="离散数学",
        credits=Decimal("3.00"),
        category="专业必修",
        sourceRefIds=["source:demo"],
    ),
    Course(
        courseCode="AI300",
        name="人工智能",
        credits=Decimal("3.00"),
        category="专业选修",
        sourceRefIds=["source:demo"],
    ),
)


def _offering(course: str, class_id: str, teacher: str) -> CourseOffering:
    return CourseOffering(
        courseCode=course,
        classId=class_id,
        teacherKey=teacher,
        teacherText="演示教师",
        credits=Decimal("3.00"),
        capacity=40,
        meetingTextRaw="周三第7-8节",
        meetings=[Meeting(dayOfWeek=3, sectionStart=7, sectionEnd=8, weeks=[1])],
        parseStatus="PARSED",
        sourceRefId=f"source:{class_id}",
    )


def _validation(verifier_id: str) -> PlanValidation:
    return PlanValidation(
        verifierResultId=verifier_id,
        verdict="UNKNOWN",
        scope="REAL_TIMETABLE",
        curriculumSnapshotId="curr:demo",
        offeringSnapshotId="offer:demo",
        recordRevision=1,
        violations=[],
        unknownChecks=[
            Issue(
                code="SECTION_UNASSIGNED",
                message="未指定班次，不能声称无冲突",
                field="items",
                retryable=False,
            )
        ],
        performedChecks=["COURSE_EXISTS"],
        sourceRefIds=["source:demo"],
    )


class ScriptedTools:
    def __init__(self, completed: tuple[CompletedCourse, ...] = ()) -> None:
        self.completed = completed
        self.calls: list[str] = []
        self.validation_items: list[PlanItem] = []
        self.fail_on: set[str] = set()
        self.reuse_verifier_id: str | None = None
        self.snapshots: list[SnapshotSummary] = []

    def call(self, tool: str, dto, context, *, params=None):
        del context
        self.calls.append(tool)
        if tool in self.fail_on:
            raise ToolUnavailable(tool)
        if tool == "listCourses":
            assert params is not None and params["curriculumSnapshotId"] == "curr:demo"
            return list(_CURRICULUM)
        if tool == "listOfferings":
            assert params is not None and params["courseCode"] is not None
            rows = {
                "CS101": [_offering("CS101", "class:cs-a", "teacher:a")],
                "AI300": [
                    _offering("AI300", "class:ai-a", "teacher:ai"),
                    _offering("AI300", "class:ai-b", "teacher:ai2"),
                ],
            }
            return rows.get(params["courseCode"], [])
        if tool == "getAcademicRecord":
            return AcademicRecord(
                academicRecordId="record:demo",
                revision=1,
                curriculumSnapshotId="curr:demo",
                completedCourses=list(self.completed),
                transcriptComplete=False,
                sourceKind="SYNTHETIC",
                createdAt="2026-11-01T00:00:00Z",
            )
        if tool == "validatePlan":
            self.validation_items = list(dto.items)
            verifier_id = self.reuse_verifier_id or f"verify:add-{len(self.calls)}"
            return _validation(verifier_id)
        if tool == "listOfferingSnapshots":
            return list(self.snapshots)
        raise AssertionError(tool)


def _plan(client: TestClient, session_id: str, *, items=None, offering="offer:demo") -> None:
    client.app.state.plan_store.remember(
        session_id=session_id,
        plan_id="plan:old",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id=offering,
        academic_record_id="record:demo",
        mode="REAL",
        items=items
        if items is not None
        else [PlanItem(courseCode="MATH201", teacherKey="teacher:math", classId="class:math")],
        hard_constraints=[],
        verifier_result_id="verify:old",
    )


def _session(client: TestClient) -> tuple[str, str]:
    data = client.post("/api/v1/sessions").json()["data"]
    return data["sessionId"], data["sessionToken"]


def _headers(token: str, key: str | None = "idem:add-1") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "X-Request-Id": "req:add-1"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _client(tools) -> TestClient:
    return TestClient(create_app(Settings(), tool_client=tools))


def _add(client: TestClient, token: str, body: dict, key: str = "idem:add-1"):
    return client.post("/api/v1/session-plans/add-course", json=body, headers=_headers(token, key))


def test_add_without_class_appends_course_and_revalidates_whole_plan() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "CS101"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["previousPlanId"] == "plan:old"
    assert data["empty"] is False
    assert data["items"] == [
        {"courseCode": "MATH201", "teacherKey": "teacher:math", "classId": "class:math"},
        {"courseCode": "CS101", "teacherKey": None, "classId": None},
    ]
    assert data["verification"]["verdict"] == "UNKNOWN"
    assert [item.courseCode for item in tools.validation_items] == ["MATH201", "CS101"]
    assert tools.calls.count("validatePlan") == 1
    saved = client.app.state.plan_store.get(session_id, data["planId"])
    assert saved is not None and len(saved.items) == 2


def test_add_with_class_takes_teacher_from_that_class() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(
        client,
        token,
        {"previousPlanId": "plan:old", "courseCode": "AI300", "classId": "class:ai-b"},
    )

    assert response.status_code == 200
    added = response.json()["data"]["items"][-1]
    assert added == {"courseCode": "AI300", "teacherKey": "teacher:ai2", "classId": "class:ai-b"}
    assert tools.validation_items[-1].classId == "class:ai-b"


def test_course_already_in_plan_is_refused_before_java() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "MATH201"})

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "COURSE_ALREADY_IN_PLAN"
    assert response.json()["issues"][0]["field"] == "courseCode"
    assert "validatePlan" not in tools.calls


@pytest.mark.parametrize("outcome", ["PASSED", "IN_PROGRESS"])
def test_passed_or_in_progress_course_is_refused(outcome: str) -> None:
    tools = ScriptedTools(
        completed=(
            CompletedCourse(
                courseCode="CS101",
                earnedCredits=Decimal("4.00") if outcome == "PASSED" else None,
                outcome=outcome,
                completedTerm="2025-2026-2",
            ),
        )
    )
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "CS101"})

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "COURSE_ALREADY_TAKEN"
    assert "validatePlan" not in tools.calls


def test_failed_course_may_be_added_again() -> None:
    tools = ScriptedTools(
        completed=(
            CompletedCourse(
                courseCode="CS101",
                earnedCredits=None,
                outcome="FAILED",
                completedTerm="2025-2026-2",
            ),
        )
    )
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "CS101"})

    assert response.status_code == 200


def test_course_in_neither_snapshot_is_not_found() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "PHYS110"})

    assert response.status_code == 404
    assert response.json()["issues"][0]["field"] == "courseCode"
    assert "validatePlan" not in tools.calls


def test_class_not_offered_for_this_course_is_not_found() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(
        client,
        token,
        {"previousPlanId": "plan:old", "courseCode": "CS101", "classId": "class:ai-a"},
    )

    assert response.status_code == 404
    assert response.json()["issues"][0]["field"] == "classId"
    assert "validatePlan" not in tools.calls


def test_class_on_plan_without_offering_snapshot_is_refused() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id, offering=None)

    with_class = _add(
        client,
        token,
        {"previousPlanId": "plan:old", "courseCode": "CS101", "classId": "class:cs-a"},
        key="idem:no-snap-class",
    )
    without_class = _add(
        client,
        token,
        {"previousPlanId": "plan:old", "courseCode": "CS101"},
        key="idem:no-snap-plain",
    )

    assert with_class.status_code == 422
    assert with_class.json()["issues"][0]["code"] == "OFFERING_SNAPSHOT_MISSING"
    assert without_class.status_code == 200
    assert without_class.json()["data"]["items"][-1]["classId"] is None


def test_foreign_plan_is_hidden_as_not_in_session() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    owner_id, _owner_token = _session(client)
    _other_id, other_token = _session(client)
    _plan(client, owner_id)

    response = _add(
        client,
        other_token,
        {"previousPlanId": "plan:old", "courseCode": "CS101"},
        key="idem:foreign-add",
    )

    assert response.status_code == 404
    assert response.json()["issues"][0]["message"] == "方案不在当前会话"
    assert tools.calls == []


def test_full_plan_is_refused() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    full = [
        PlanItem(courseCode=f"ELEC{index:03d}", teacherKey=None, classId=None)
        for index in range(30)
    ]
    _plan(client, session_id, items=full)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "CS101"})

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "PLAN_FULL"
    assert "validatePlan" not in tools.calls


def test_java_unavailable_stays_503_and_saves_nothing() -> None:
    tools = ScriptedTools()
    tools.fail_on.add("validatePlan")
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "CS101"})

    assert response.status_code == 503
    assert response.json()["issues"][0]["code"] == "TOOL_UNAVAILABLE"
    assert client.app.state.plan_store.plan_ids(session_id) == ["plan:old"]


def test_reused_verifier_id_is_refused() -> None:
    tools = ScriptedTools()
    tools.reuse_verifier_id = "verify:old"
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(
        client, token, {"previousPlanId": "plan:old", "courseCode": "CS101"}, key="idem:reuse"
    )

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "VERIFICATION_REUSED"
    assert client.app.state.plan_store.plan_ids(session_id) == ["plan:old"]


def test_same_idempotency_key_does_not_add_twice() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)
    body = {"previousPlanId": "plan:old", "courseCode": "CS101"}

    first = _add(client, token, body, key="idem:twice")
    second = _add(client, token, body, key="idem:twice")

    assert first.status_code == 200
    assert second.json() == first.json()
    assert tools.calls.count("validatePlan") == 1
    assert len(client.app.state.plan_store.plan_ids(session_id)) == 2


def test_extra_owner_field_is_rejected_by_the_gateway() -> None:
    tools = ScriptedTools()
    client = _client(tools)
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(
        client,
        token,
        {"previousPlanId": "plan:old", "courseCode": "CS101", "ownerId": "someone-else"},
        key="idem:owner",
    )

    assert response.status_code == 422
    assert tools.calls == []


def test_fake_catalog_never_yields_a_valid_verdict_for_an_added_course() -> None:
    client = _client(TypedFakeToolClient())
    session_id, token = _session(client)
    _plan(client, session_id)

    response = _add(client, token, {"previousPlanId": "plan:old", "courseCode": "CS101"})

    # The fake catalog lists CS101 and has no offerings, so the add reaches Java,
    # and the fake Java answer is UNKNOWN. It must come back unchanged, not VALID.
    assert response.status_code == 200
    assert response.json()["data"]["verification"]["verdict"] == "UNKNOWN"


def test_planning_response_names_the_timetable_reference() -> None:
    body = json.loads(
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("contracts/examples/planning-request.json")
        .read_text(encoding="utf-8")
    )
    body["offeringSnapshotId"] = "offer:demo"

    class SnapshotTools(TypedFakeToolClient):
        def call(self, tool, dto, context, *, params=None, idempotency_key=None):
            if tool == "listOfferingSnapshots":
                return [
                    SnapshotSummary(
                        snapshotId="offer:demo",
                        kind="OFFERING",
                        state="PUBLISHED",
                        sourceKind="OFFICIAL_DOCUMENT",
                        termId="2026-2027-1",
                        createdAt="2026-10-01T00:00:00Z",
                        displayName=None,
                        sourceValidation="UNVERIFIED",
                    )
                ]
            return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)

    client = _client(SnapshotTools())
    _session_id, token = _session(client)
    response = client.post(
        "/api/v1/planning",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Request-Id": "req:ctx-1",
            "Idempotency-Key": "idem:ctx-1",
        },
    )

    assert response.status_code == 200, response.text
    context = response.json()["data"]["planningContext"]
    assert context == {
        "targetTerm": "NEXT_SEMESTER",
        "timetableReferenceSnapshotId": "offer:demo",
        "timetableReferenceTermId": "2026-2027-1",
        "timetableSourceValidation": "UNVERIFIED",
    }
