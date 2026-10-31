from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from agent_runtime.adapters.model_client import (
    AdviceChatModelReply,
    FakeModelAdapter,
    ModelInvalidOutput,
)
from agent_runtime.adapters.tool_client import ToolRejected
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import AcademicRecord, Course, ReviewNote, SnapshotSummary
from agent_runtime.api.schemas.advice_chat import AdviceChatRequest
from agent_runtime.application.advice_chat import AdviceChatService
from agent_runtime.application.context import ExecutionContext


class ChatTools:
    def __init__(self):
        self.calls = []

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        self.calls.append((tool, params))
        if tool == "getSchoolProgress":
            raise ToolRejected(tool, 404, "NOT_VISIBLE", "no progress")
        if tool == "listCurricula":
            return [
                SnapshotSummary(
                    snapshotId="curr:1",
                    kind="CURRICULUM",
                    state="PUBLISHED",
                    sourceKind="CURRICULUM_FILE",
                    termId=None,
                    createdAt=datetime.now(UTC),
                    sourceValidation="UNVERIFIED",
                    displayName="测试培养方案",
                )
            ]
        if tool == "listCourses":
            return [
                Course(
                    courseCode="CS301",
                    name="人工智能",
                    credits=Decimal("3.00"),
                    category="专业选修课",
                    sourceRefIds=["src:1"],
                    suggestedTerm=None,
                ),
                Course(
                    courseCode="CS302",
                    name="数据库系统",
                    credits=Decimal("3.00"),
                    category="专业选修课",
                    sourceRefIds=["src:3"],
                    suggestedTerm=None,
                ),
                Course(
                    courseCode="CS303",
                    name="机器学习",
                    credits=Decimal("3.00"),
                    category="高年级研讨课",
                    sourceRefIds=["src:4"],
                    suggestedTerm=None,
                ),
                Course(
                    courseCode="CS101",
                    name="程序设计",
                    credits=Decimal("3.00"),
                    category="公共基础课",
                    sourceRefIds=["src:2"],
                    suggestedTerm=None,
                ),
            ]
        if tool == "searchReviews":
            return [
                ReviewNote(
                    reviewNoteId="review:1",
                    courseCode=params["courseCode"],
                    teacherKey=None,
                    termId=None,
                    sourceKind="USER_IMPORT",
                    publishedAt=None,
                    sourceUrl=None,
                    excerpt="课程评价",
                    dimensions=[],
                    matchStatus="COURSE_ONLY",
                    sourceRefId="src:review",
                    teacherDisplayName=None,
                )
            ]
        raise AssertionError(tool)


class ChatModel:
    def __init__(self, course_code="CS301", refs=None):
        self.calls = 0
        self.course_code = course_code
        self.refs = refs or []
        self.messages = []

    def generate_chat(self, *, context, messages):
        self.calls += 1
        self.messages = messages
        assert "grade" not in messages[0]["content"]
        return AdviceChatModelReply(
            reply="建议先了解课程内容。",
            question=None,
            courses=[
                {
                    "courseCode": self.course_code,
                    "reason": "与兴趣方向相关。",
                    "reviewNoteIds": self.refs,
                }
            ],
            suggestions=[{"kind": "SELECT_COURSE", "label": "加入待选", "value": self.course_code}],
            input_tokens=10,
            output_tokens=8,
        )


def _request():
    return AdviceChatRequest.model_validate(
        {
            "schemaVersion": "1.0",
            "curriculumSnapshotId": "curr:1",
            "academicRecordId": None,
            "mode": "REAL",
            "message": "推荐人工智能课程",
            "history": [],
            "interestText": "人工智能",
            "selectedCourseCodes": [],
        }
    )


def _context():
    return ExecutionContext(
        subject_id="session:1",
        request_id="req:1",
        curriculum_snapshot_id="curr:1",
        offering_snapshot_id=None,
        model_id="test",
        temperature=0,
        deadline=datetime.now(UTC),
        harness_version="test",
    )


def test_chat_uses_default_candidate_scope_and_keeps_fake_marked():
    tools = ChatTools()
    answer = AdviceChatService(tool_client=tools, model_adapter=FakeModelAdapter()).run(
        _request(), _context()
    )
    assert [item.courseCode for item in answer.courses] == ["CS301", "CS302", "CS303"]
    assert any(item.reviewStatus == "NOT_QUERIED" for item in answer.courses)
    assert any(issue.code == "FAKE_MODEL" for issue in answer.unknowns)
    assert answer.usage.toolCalls == 5
    assert len(tools.calls) == 5


def test_chat_rejects_model_course_and_review_not_in_shown_facts(caplog):
    tools = ChatTools()
    caplog.set_level(logging.WARNING, logger="agent_runtime.application.advice_chat")
    with pytest.raises(ModelInvalidOutput, match="课程引用不匹配") as caught:
        AdviceChatService(tool_client=tools, model_adapter=ChatModel("CS999")).run(
            _request(), _context()
        )
    assert caught.value.diagnostics["field_path"] == "courses[0].courseCode"
    assert caught.value.diagnostics["reason_code"] == "COURSE_REFERENCE_MISMATCH"
    assert caught.value.diagnostics["input_tokens"] == 10
    assert "CS999" not in caplog.text

    with pytest.raises(ModelInvalidOutput, match="课程评价引用不匹配") as caught:
        AdviceChatService(
            tool_client=tools, model_adapter=ChatModel("CS301", ["review:other"])
        ).run(_request(), _context())
    assert caught.value.diagnostics["field_path"] == "courses[0].reviewNoteIds"
    assert caught.value.diagnostics["reason_code"] == "REVIEW_REFERENCE_MISMATCH"


def test_chat_uses_matching_school_progress_record_when_id_is_omitted():
    class ProgressTools(ChatTools):
        def call(self, tool, dto, context, *, params=None, idempotency_key=None):
            if tool == "getSchoolProgress":
                from agent_runtime.api.schemas import SchoolProgressImportResult

                return SchoolProgressImportResult.model_validate(
                    {
                        "receipt": {
                            "schoolProgressId": "progress:1",
                            "contentHash": "a" * 64,
                            "importedAt": datetime.now(UTC).isoformat(),
                            "reused": True,
                        },
                        "snapshot": {
                            "format": "coursepilot-shu-academic-progress",
                            "version": 1,
                            "capturedAt": datetime.now(UTC).isoformat(),
                            "source": "browser adapter",
                            "nodes": [
                                {
                                    "nodeId": "node:1",
                                    "parentId": None,
                                    "schoolNodeId": None,
                                    "leaf": True,
                                    "name": "专业选修",
                                    "requiredCredits": 3,
                                    "earnedCredits": 0,
                                    "remainingCredits": 3,
                                }
                            ],
                            "courses": [],
                        },
                        "academicRecord": {
                            "academicRecordId": "record:school",
                            "revision": 1,
                            "curriculumSnapshotId": "curr:1",
                            "completedCourses": [
                                {
                                    "courseCode": "CS301",
                                    "earnedCredits": 3,
                                    "outcome": "PASSED",
                                    "completedTerm": "2025-2026-1",
                                }
                            ],
                            "transcriptComplete": True,
                            "sourceKind": "USER_IMPORT",
                            "createdAt": datetime.now(UTC).isoformat(),
                        },
                    }
                )
            return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)

    answer = AdviceChatService(tool_client=ProgressTools(), model_adapter=FakeModelAdapter()).run(
        _request(), _context()
    )
    assert "CS301" not in {item.courseCode for item in answer.courses}
    assert not any(issue.code == "ACADEMIC_RECORD_MISSING" for issue in answer.unknowns)


def test_explicit_record_id_does_not_reuse_mismatched_school_progress():
    class ProgressTools(ChatTools):
        def call(self, tool, dto, context, *, params=None, idempotency_key=None):
            if tool == "getSchoolProgress":
                from agent_runtime.api.schemas import SchoolProgressImportResult

                return SchoolProgressImportResult.model_validate(
                    {
                        "receipt": {
                            "schoolProgressId": "progress:1",
                            "contentHash": "b" * 64,
                            "importedAt": datetime.now(UTC).isoformat(),
                            "reused": True,
                        },
                        "snapshot": {
                            "format": "coursepilot-shu-academic-progress",
                            "version": 1,
                            "capturedAt": datetime.now(UTC).isoformat(),
                            "source": "browser adapter",
                            "nodes": [
                                {
                                    "nodeId": "node:1",
                                    "parentId": None,
                                    "schoolNodeId": None,
                                    "leaf": True,
                                    "name": "专业选修",
                                    "requiredCredits": 3,
                                    "earnedCredits": 0,
                                    "remainingCredits": 3,
                                }
                            ],
                            "courses": [],
                        },
                        "academicRecord": {
                            "academicRecordId": "record:school",
                            "revision": 1,
                            "curriculumSnapshotId": "curr:1",
                            "completedCourses": [],
                            "transcriptComplete": False,
                            "sourceKind": "USER_IMPORT",
                            "createdAt": datetime.now(UTC).isoformat(),
                        },
                    }
                )
            if tool == "getAcademicRecord":
                assert params["recordId"] == "record:selected"
                return AcademicRecord(
                    academicRecordId="record:selected",
                    revision=1,
                    curriculumSnapshotId="curr:1",
                    completedCourses=[],
                    transcriptComplete=False,
                    sourceKind="USER_IMPORT",
                    createdAt=datetime.now(UTC),
                )
            return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)

    request = _request().model_copy(update={"academicRecordId": "record:selected"})
    model = ChatModel()
    answer = AdviceChatService(tool_client=ProgressTools(), model_adapter=model).run(
        request, _context()
    )
    assert answer.schoolProgress is None
    assert any(issue.code == "SCHOOL_PROGRESS_RECORD_MISMATCH" for issue in answer.unknowns)
    assert '"schoolProgress": null' in model.messages[0]["content"]


def test_chat_http_idempotent_replay_does_not_call_model_twice():
    tools = ChatTools()
    app = create_app(tool_client=tools)
    model = ChatModel()
    app.state.advice_chat = AdviceChatService(tool_client=tools, model_adapter=model)
    client = TestClient(app)
    session = client.post("/api/v1/sessions").json()["data"]
    token = session["sessionToken"]
    body = _request().model_dump(mode="json")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Request-Id": "req:chat",
        "Idempotency-Key": "chat:1",
    }
    first = client.post("/api/v1/advice/chat", json=body, headers=headers)
    replay = client.post("/api/v1/advice/chat", json=body, headers=headers)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert model.calls == 1
    assert app.state.spend_ledger.spent(session["sessionId"])[0] == 10


def test_chat_http_classifies_reference_failure_without_echoing_course_value():
    tools = ChatTools()
    app = create_app(tool_client=tools)
    model = ChatModel("CS999")
    app.state.advice_chat = AdviceChatService(tool_client=tools, model_adapter=model)
    client = TestClient(app)
    session = client.post("/api/v1/sessions").json()["data"]
    response = client.post(
        "/api/v1/advice/chat",
        json=_request().model_dump(mode="json"),
        headers={
            "Authorization": f"Bearer {session['sessionToken']}",
            "X-Request-Id": "req:classified",
            "Idempotency-Key": "chat:classified",
        },
    )
    assert response.status_code == 422
    issue = response.json()["issues"][0]
    assert issue["message"] == "课程引用不匹配"
    assert issue["field"] == "courses[0].courseCode"
    assert "CS999" not in response.text
    assert model.calls == 1


def test_chat_caches_paid_terminal_failure_and_new_key_runs_again():
    class FailingModel:
        def __init__(self):
            self.calls = 0

        def generate_chat(self, *, context, messages):
            self.calls += 1
            raise ModelInvalidOutput(
                "controlled malformed output", input_tokens=10, output_tokens=8
            )

    tools = ChatTools()
    app = create_app(tool_client=tools)
    model = FailingModel()
    app.state.advice_chat = AdviceChatService(tool_client=tools, model_adapter=model)
    client = TestClient(app)
    session = client.post("/api/v1/sessions").json()["data"]
    body = _request().model_dump(mode="json")
    headers = {
        "Authorization": f"Bearer {session['sessionToken']}",
        "X-Request-Id": "req:failure",
        "Idempotency-Key": "chat:failed",
    }

    first = client.post("/api/v1/advice/chat", json=body, headers=headers)
    replay = client.post("/api/v1/advice/chat", json=body, headers=headers)
    assert first.status_code == replay.status_code == 422
    assert first.json() == replay.json()
    assert model.calls == 1
    assert app.state.spend_ledger.spent(session["sessionId"]) == (10, 8)

    changed_key = {**headers, "Idempotency-Key": "chat:failed-retry"}
    retry = client.post("/api/v1/advice/chat", json=body, headers=changed_key)
    assert retry.status_code == 422
    assert model.calls == 2
    assert app.state.spend_ledger.spent(session["sessionId"]) == (20, 16)
