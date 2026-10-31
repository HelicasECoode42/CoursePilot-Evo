"""Session offering search and one-course replacement.

The scripted tool stands in for Java. It can return INVALID or UNKNOWN, and it
can be unavailable. None of those outcomes may be stored as a fresh VALID plan.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import FakeModelAdapter
from agent_runtime.adapters.tool_client import ToolUnavailable
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import (
    Constraint,
    CourseOffering,
    Issue,
    Meeting,
    PlanItem,
    PlanningRequest,
    PlanValidation,
)
from agent_runtime.api.settings import Settings
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.plan_replacement import ReusedVerification
from agent_runtime.application.plan_store import PlanNotInSession, SessionPlanStore
from agent_runtime.application.runner import PlanningRunner

_CONSTRAINT = Constraint(
    kind="BLOCK_DAY",
    courseCode=None,
    teacherKey=None,
    dayOfWeek=1,
    section=None,
    value=None,
    sourceText="周一不能排课",
)


class ScriptedTools:
    def __init__(self, verdict: str = "INVALID") -> None:
        self.verdict = verdict
        self.calls: list[str] = []
        self.validation_request = None
        self.fail_on: set[str] = set()
        self.reuse_verifier_id: str | None = None
        self._validations = 0

    def call(self, tool: str, dto, context, *, params=None):
        del context
        self.calls.append(tool)
        if tool in self.fail_on:
            raise ToolUnavailable(tool)
        if tool == "listOfferings":
            assert params is not None
            assert params["curriculumSnapshotId"] == "curr:demo"
            assert params["offeringSnapshotId"] == "offer:demo"
            assert params["courseCode"] == "CS101"
            return [_offering("class:cs-a", "teacher:a"), _offering("class:cs-b", "teacher:b")]
        if tool == "validatePlan":
            self._validations += 1
            self.validation_request = dto
            verifier_id = self.reuse_verifier_id or f"verify:new-{self._validations}"
            return _validation(self.verdict, verifier_id)
        raise AssertionError(tool)


def _offering(class_id: str, teacher_key: str) -> CourseOffering:
    return CourseOffering(
        courseCode="CS101",
        classId=class_id,
        teacherKey=teacher_key,
        teacherText="演示教师",
        credits=Decimal("4.00"),
        capacity=40,
        meetingTextRaw="周一第1-2节",
        meetings=[Meeting(dayOfWeek=1, sectionStart=1, sectionEnd=2, weeks=[1])],
        parseStatus="PARSED",
        sourceRefId=f"source:{class_id}",
    )


def _validation(verdict: str, verifier_id: str) -> PlanValidation:
    unknown = verdict == "UNKNOWN"
    return PlanValidation(
        verifierResultId=verifier_id,
        verdict=verdict,  # type: ignore[arg-type]
        scope="REAL_TIMETABLE",
        curriculumSnapshotId="curr:demo",
        offeringSnapshotId="offer:demo",
        recordRevision=1,
        violations=[]
        if unknown
        else [
            Issue(
                code="TIME_CONFLICT",
                message="与 MATH201 的周一第1节冲突",
                field="items",
                retryable=False,
            )
        ],
        unknownChecks=[
            Issue(
                code="TIME_UNPARSED",
                message="上课时间无法解析，不能当成无冲突",
                field="meetings",
                retryable=False,
            )
        ]
        if unknown
        else [],
        performedChecks=["TIME_OVERLAP"],
        sourceRefIds=["source:class:cs-b"],
    )


def _remember(app, session_id: str, *, offering: str | None = "offer:demo") -> None:
    app.state.plan_store.remember(
        session_id=session_id,
        plan_id="plan:old",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id=offering,
        academic_record_id="record:demo",
        mode="REAL",
        items=[
            PlanItem(courseCode="CS101", teacherKey="teacher:old", classId="class:old"),
            PlanItem(courseCode="MATH201", teacherKey="teacher:math", classId="class:math"),
        ],
        hard_constraints=[_CONSTRAINT],
        verifier_result_id="verify:old",
    )


def _session(client: TestClient) -> tuple[str, str]:
    data = client.post("/api/v1/sessions").json()["data"]
    return data["sessionId"], data["sessionToken"]


def _headers(token: str, *, key: str | None = "idem:replace-1") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "X-Request-Id": "req:replace-1"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _app(tools) -> TestClient:
    app = create_app(Settings(), tool_client=tools)
    return TestClient(app)


def test_search_returns_multiple_classes_for_the_course() -> None:
    tools = ScriptedTools()
    client = _app(tools)
    session_id, token = _session(client)
    _remember(client.app, session_id)

    response = client.get(
        "/api/v1/session-offerings",
        params={"previousPlanId": "plan:old", "courseCode": "CS101"},
        headers=_headers(token, key=None),
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["classId"] for item in items] == ["class:cs-a", "class:cs-b"]
    assert items[0]["parseStatus"] == "PARSED"
    assert items[0]["sourceRefId"] == "source:class:cs-a"
    assert tools.calls == ["listOfferings"]


def test_replace_keeps_other_courses_and_passes_java_verdict_through() -> None:
    tools = ScriptedTools(verdict="INVALID")
    client = _app(tools)
    session_id, token = _session(client)
    _remember(client.app, session_id)

    response = client.post(
        "/api/v1/session-plans/replace",
        json={"previousPlanId": "plan:old", "courseCode": "CS101", "selectedClassId": "class:cs-b"},
        headers=_headers(token),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["previousPlanId"] == "plan:old"
    assert data["planId"] != "plan:old"
    assert data["items"][0] == {
        "courseCode": "CS101",
        "teacherKey": "teacher:b",
        "classId": "class:cs-b",
    }
    assert data["items"][1] == {
        "courseCode": "MATH201",
        "teacherKey": "teacher:math",
        "classId": "class:math",
    }
    assert data["hardConstraints"] == [_CONSTRAINT.model_dump(mode="json")]
    assert data["verification"]["verdict"] == "INVALID"
    assert data["verification"]["verifierResultId"] == "verify:new-1"
    assert data["verification"]["violations"][0]["message"] == "与 MATH201 的周一第1节冲突"
    assert tools.validation_request is not None
    assert [item.courseCode for item in tools.validation_request.items] == ["CS101", "MATH201"]
    assert tools.validation_request.hardConstraints[0].sourceText == "周一不能排课"
    assert client.app.state.plan_store.plan_ids(session_id) == ["plan:old", data["planId"]]


def test_remove_course_is_deterministic_and_revalidates_remaining_plan() -> None:
    tools = ScriptedTools(verdict="UNKNOWN")
    client = _app(tools)
    session_id, token = _session(client)
    _remember(client.app, session_id)
    client.app.state.plan_store.remember(
        session_id=session_id,
        plan_id="plan:pinned",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id="offer:demo",
        academic_record_id="record:demo",
        mode="REAL",
        items=[
            PlanItem(courseCode="CS101", teacherKey="teacher:old", classId="class:old"),
            PlanItem(courseCode="MATH201", teacherKey="teacher:math", classId="class:math"),
        ],
        hard_constraints=[
            _CONSTRAINT,
            Constraint(
                kind="PIN_COURSE",
                courseCode="CS101",
                teacherKey=None,
                dayOfWeek=None,
                section=None,
                value=None,
                sourceText="必修",
            ),
            Constraint(
                kind="PIN_TEACHER_COURSE",
                courseCode="CS101",
                teacherKey="teacher:old",
                dayOfWeek=None,
                section=None,
                value=None,
                sourceText="指定教师",
            ),
        ],
        verifier_result_id="verify:pinned",
    )
    response = client.post(
        "/api/v1/session-plans/remove-course",
        json={"previousPlanId": "plan:pinned", "courseCode": "CS101"},
        headers=_headers(token, key="idem:remove-cs101"),
    )
    data = response.json()["data"]
    assert response.status_code == 200
    assert data["items"] == [
        {"courseCode": "MATH201", "teacherKey": "teacher:math", "classId": "class:math"}
    ]
    assert data["hardConstraints"] == [_CONSTRAINT.model_dump(mode="json")]
    assert data["verification"]["verdict"] == "UNKNOWN"
    assert tools.calls == ["validatePlan"]
    saved = client.app.state.plan_store.get(session_id, data["planId"])
    assert saved is not None and [item.courseCode for item in saved.items] == ["MATH201"]


def test_removing_last_course_saves_explicit_empty_plan_without_java_call() -> None:
    tools = ScriptedTools()
    client = _app(tools)
    session_id, token = _session(client)
    client.app.state.plan_store.remember(
        session_id=session_id,
        plan_id="plan:single",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id="offer:demo",
        academic_record_id="record:demo",
        mode="REAL",
        items=[PlanItem(courseCode="CS101", teacherKey="teacher:old", classId="class:old")],
        hard_constraints=[_CONSTRAINT],
        verifier_result_id="verify:single",
    )
    body = {"previousPlanId": "plan:single", "courseCode": "CS101"}
    headers = _headers(token, key="idem:remove-last")
    first = client.post("/api/v1/session-plans/remove-course", json=body, headers=headers)
    second = client.post("/api/v1/session-plans/remove-course", json=body, headers=headers)
    data = first.json()["data"]
    assert first.status_code == 200
    assert data["items"] == [] and data["empty"] is True and data["verification"] is None
    assert second.json() == first.json()
    assert tools.calls == []


def test_unknown_verdict_is_not_rewritten() -> None:
    tools = ScriptedTools(verdict="UNKNOWN")
    client = _app(tools)
    session_id, token = _session(client)
    _remember(client.app, session_id)

    response = client.post(
        "/api/v1/session-plans/replace",
        json={"previousPlanId": "plan:old", "courseCode": "CS101", "selectedClassId": "class:cs-a"},
        headers=_headers(token),
    )

    verification = response.json()["data"]["verification"]
    assert response.status_code == 200
    assert verification["verdict"] == "UNKNOWN"
    assert verification["unknownChecks"][0]["code"] == "TIME_UNPARSED"


def test_same_idempotency_key_does_not_create_a_second_plan() -> None:
    tools = ScriptedTools()
    client = _app(tools)
    session_id, token = _session(client)
    _remember(client.app, session_id)
    body = {"previousPlanId": "plan:old", "courseCode": "CS101", "selectedClassId": "class:cs-b"}
    headers = _headers(token)

    first = client.post("/api/v1/session-plans/replace", json=body, headers=headers)
    second = client.post("/api/v1/session-plans/replace", json=body, headers=headers)

    assert first.status_code == 200
    assert second.json() == first.json()
    assert tools.calls.count("validatePlan") == 1
    assert len(client.app.state.plan_store.plan_ids(session_id)) == 2


def test_foreign_plan_and_unknown_class_are_rejected() -> None:
    tools = ScriptedTools()
    client = _app(tools)
    owner_id, owner_token = _session(client)
    _other_id, other_token = _session(client)
    _remember(client.app, owner_id)

    foreign = client.post(
        "/api/v1/session-plans/replace",
        json={"previousPlanId": "plan:old", "courseCode": "CS101", "selectedClassId": "class:cs-a"},
        headers=_headers(other_token),
    )
    rejected = client.post(
        "/api/v1/session-plans/replace",
        json={
            "previousPlanId": "plan:old",
            "courseCode": "CS101",
            "selectedClassId": "class:missing",
        },
        headers=_headers(owner_token, key="idem:missing-class"),
    )
    foreign_remove = client.post(
        "/api/v1/session-plans/remove-course",
        json={"previousPlanId": "plan:old", "courseCode": "CS101"},
        headers=_headers(other_token, key="idem:foreign-remove"),
    )

    assert foreign.status_code == 404
    assert foreign.json()["issues"][0]["message"] == "方案不在当前会话"
    assert rejected.status_code == 404
    assert rejected.json()["issues"][0]["field"] == "selectedClassId"
    assert foreign_remove.status_code == 404
    assert foreign_remove.json()["issues"][0]["message"] == "方案不在当前会话"
    assert "validatePlan" not in tools.calls
    assert client.app.state.plan_store.plan_ids(owner_id) == ["plan:old"]


def test_missing_course_and_missing_snapshot_do_not_call_java() -> None:
    tools = ScriptedTools()
    client = _app(tools)
    session_id, token = _session(client)
    _remember(client.app, session_id)

    missing_course = client.post(
        "/api/v1/session-plans/replace",
        json={
            "previousPlanId": "plan:old",
            "courseCode": "PHYS110",
            "selectedClassId": "class:cs-a",
        },
        headers=_headers(token),
    )
    client.app.state.plan_store.remember(
        session_id=session_id,
        plan_id="plan:no-snapshot",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id=None,
        academic_record_id="record:demo",
        mode="REAL",
        items=[PlanItem(courseCode="CS101", teacherKey=None, classId=None)],
        hard_constraints=[_CONSTRAINT],
        verifier_result_id="verify:old",
    )
    missing_snapshot = client.get(
        "/api/v1/session-offerings",
        params={"previousPlanId": "plan:no-snapshot", "courseCode": "CS101"},
        headers=_headers(token, key=None),
    )

    missing_replace = client.post(
        "/api/v1/session-plans/replace",
        json={
            "previousPlanId": "plan:no-snapshot",
            "courseCode": "CS101",
            "selectedClassId": "class:cs-a",
        },
        headers=_headers(token, key="idem:no-snapshot"),
    )

    assert missing_course.status_code == 422
    assert missing_course.json()["issues"][0]["message"] == "方案里没有这门课"
    assert missing_snapshot.status_code == 200
    assert missing_snapshot.json()["status"] == "UNKNOWN"
    assert missing_snapshot.json()["data"]["items"] == []
    assert missing_snapshot.json()["issues"][0]["code"] == "OFFERING_SNAPSHOT_MISSING"
    assert missing_snapshot.json()["issues"][0]["field"] is None
    assert missing_replace.status_code == 422
    assert missing_replace.json()["issues"][0]["field"] is None
    assert "班次快照" in missing_replace.json()["issues"][0]["message"]
    assert tools.calls == []


def test_java_unavailable_stays_503_and_reused_verdict_is_refused() -> None:
    tools = ScriptedTools()
    tools.fail_on.add("listOfferings")
    client = _app(tools)
    session_id, token = _session(client)
    _remember(client.app, session_id)
    body = {"previousPlanId": "plan:old", "courseCode": "CS101", "selectedClassId": "class:cs-b"}

    unavailable = client.post("/api/v1/session-plans/replace", json=body, headers=_headers(token))
    tools.fail_on.clear()
    tools.reuse_verifier_id = "verify:old"
    reused = client.post(
        "/api/v1/session-plans/replace",
        json=body,
        headers=_headers(token, key="idem:reused"),
    )

    assert unavailable.status_code == 503
    assert unavailable.json()["issues"][0]["code"] == "TOOL_UNAVAILABLE"
    assert reused.status_code == 422
    assert reused.json()["issues"][0]["code"] == "VERIFICATION_REUSED"
    assert client.app.state.plan_store.plan_ids(session_id) == ["plan:old"]


def test_fake_tool_catalog_cannot_become_a_valid_replacement() -> None:
    client = _app(TypedFakeToolClient())
    session_id, token = _session(client)
    _remember(client.app, session_id)

    response = client.post(
        "/api/v1/session-plans/replace",
        json={"previousPlanId": "plan:old", "courseCode": "CS101", "selectedClassId": "class:cs-b"},
        headers=_headers(token),
    )

    body = response.json()
    assert response.status_code == 404
    assert body["status"] == "NOT_FOUND"
    assert body["data"] == {}


def test_runner_remembers_the_recommendation_for_this_session(
    planning_request: PlanningRequest,
) -> None:
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.intent.hardConstraints = [_CONSTRAINT]
    store = SessionPlanStore()
    runner = PlanningRunner(
        tool_client=TypedFakeToolClient(),
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=FakeModelAdapter(),
        plan_store=store,
    )
    context = ExecutionContext(
        subject_id="session:demo",
        request_id="req:demo",
        curriculum_snapshot_id=planning_request.curriculumSnapshotId,
        offering_snapshot_id=planning_request.offeringSnapshotId,
        model_id="DEPLOYMENT_MODEL_PLACEHOLDER",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=45),
        harness_version="harness:v0",
    )

    answer = runner.run(planning_request, context)

    saved = store.get("session:demo", answer.recommendations[0].planId)
    assert saved is not None
    assert saved.hard_constraints[0].sourceText == "周一不能排课"
    assert saved.verifier_result_id == answer.recommendations[0].verification.verifierResultId
    assert store.get("session:other", answer.recommendations[0].planId) is None


class RecordingFake(TypedFakeToolClient):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.validation = None
        self.reuse = False

    def call(self, tool: str, dto, context, *, params=None):
        self.calls.append(tool)
        result = super().call(tool, dto, context, params=params)
        if tool == "validatePlan":
            self.validation = dto
            if self.reuse:
                return result.model_copy(update={"verifierResultId": "verify:old"})
        return result


def _planning_context(request: PlanningRequest) -> ExecutionContext:
    return ExecutionContext(
        subject_id="session:demo",
        request_id="req:replan",
        curriculum_snapshot_id=request.curriculumSnapshotId,
        offering_snapshot_id=request.offeringSnapshotId,
        model_id="DEPLOYMENT_MODEL_PLACEHOLDER",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=45),
        harness_version="harness:v0",
    )


def _replan_runner(tools: RecordingFake, store: SessionPlanStore) -> PlanningRunner:
    return PlanningRunner(
        tool_client=tools,
        harness=HarnessSnapshot(version="harness:v0", root=Path(".")),
        model_adapter=FakeModelAdapter(),
        plan_store=store,
    )


def test_replan_rejects_a_plan_from_outside_this_session(
    planning_request: PlanningRequest,
) -> None:
    planning_request.previousPlanId = "plan:missing"
    tools = RecordingFake()
    runner = _replan_runner(tools, SessionPlanStore())

    with pytest.raises(PlanNotInSession):
        runner.run(planning_request, _planning_context(planning_request))

    assert tools.calls == []


def test_replan_rechecks_the_request_constraints_and_not_the_old_verdict(
    planning_request: PlanningRequest,
) -> None:
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.intent.hardConstraints = [_CONSTRAINT]
    planning_request.previousPlanId = "plan:old"
    store = SessionPlanStore()
    store.remember(
        session_id="session:demo",
        plan_id="plan:old",
        curriculum_snapshot_id=planning_request.curriculumSnapshotId,
        offering_snapshot_id=planning_request.offeringSnapshotId,
        academic_record_id=planning_request.academicRecordId,
        mode=planning_request.mode,
        items=[PlanItem(courseCode="CS101", teacherKey=None, classId=None)],
        hard_constraints=[],
        verifier_result_id="verify:old",
    )
    tools = RecordingFake()

    answer = _replan_runner(tools, store).run(planning_request, _planning_context(planning_request))

    assert tools.validation is not None
    assert tools.validation.hardConstraints[0].sourceText == "周一不能排课"
    new_id = answer.recommendations[0].verification.verifierResultId
    assert new_id != "verify:old"
    assert store.get("session:demo", answer.recommendations[0].planId) is not None


def test_replan_refuses_a_reused_verifier_id(planning_request: PlanningRequest) -> None:
    planning_request.intent.motives = ["GPA"]
    planning_request.intent.priorityOrder = ["GPA"]
    planning_request.previousPlanId = "plan:old"
    store = SessionPlanStore()
    store.remember(
        session_id="session:demo",
        plan_id="plan:old",
        curriculum_snapshot_id=planning_request.curriculumSnapshotId,
        offering_snapshot_id=planning_request.offeringSnapshotId,
        academic_record_id=planning_request.academicRecordId,
        mode=planning_request.mode,
        items=[PlanItem(courseCode="CS101", teacherKey=None, classId=None)],
        hard_constraints=[],
        verifier_result_id="verify:old",
    )
    tools = RecordingFake()
    tools.reuse = True

    with pytest.raises(ReusedVerification):
        _replan_runner(tools, store).run(planning_request, _planning_context(planning_request))

    assert store.plan_ids("session:demo") == ["plan:old"]


def test_planning_http_hides_another_sessions_plan() -> None:
    client = _app(TypedFakeToolClient())
    _session_id, token = _session(client)
    body = json.loads(
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("contracts/examples/planning-request.json")
        .read_text(encoding="utf-8")
    )
    body["previousPlanId"] = "plan:other"

    response = client.post(
        "/api/v1/planning",
        json=body,
        headers=_headers(token, key="idem:foreign-plan"),
    )

    assert response.status_code == 404
    assert response.json()["issues"][0]["message"] == "方案不在当前会话"
    assert response.json()["issues"][0]["field"] == "previousPlanId"
