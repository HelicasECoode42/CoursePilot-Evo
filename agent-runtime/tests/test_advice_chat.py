from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

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


def test_out_of_scope_citations_are_dropped_and_answer_kept(caplog):
    caplog.set_level(logging.INFO, logger="agent_runtime.application.advice_chat")
    answer = AdviceChatService(tool_client=ChatTools(), model_adapter=ChatModel("CS999")).run(
        _request(), _context()
    )
    assert answer.reply == "建议先了解课程内容。"
    assert answer.courses == []
    assert answer.suggestions == []
    assert any(issue.code == "MODEL_CITATION_DROPPED" for issue in answer.unknowns)
    assert "CS999" not in answer.model_dump_json()
    assert "CS999" not in caplog.text


def test_foreign_review_id_is_dropped_and_course_kept():
    answer = AdviceChatService(
        tool_client=ChatTools(), model_adapter=ChatModel("CS301", ["review:other"])
    ).run(_request(), _context())
    assert [item.courseCode for item in answer.courses] == ["CS301"]
    assert answer.courses[0].reviewNoteIds == []
    assert any(issue.code == "MODEL_CITATION_DROPPED" for issue in answer.unknowns)


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


def test_chat_http_drops_unknown_course_without_echoing_course_value():
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
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["courses"] == []
    assert any(issue["code"] == "MODEL_CITATION_DROPPED" for issue in data["unknowns"])
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


def _catalog_course(code: str, name: str, category: str) -> Course:
    return Course(
        courseCode=code,
        name=name,
        credits=Decimal("3.00"),
        category=category,
        sourceRefIds=[f"src:{code}"],
        suggestedTerm=None,
    )


CATALOG = [
    _catalog_course("CS201", "线性代数", "学科基础课"),
    _catalog_course("CS205", "数据结构", "学科基础课"),
    _catalog_course("CS301", "人工智能", "专业选修课"),
    _catalog_course("CS302", "数据库系统", "专业选修课"),
    _catalog_course("CS303", "机器学习", "高年级研讨课"),
    _catalog_course("CS101", "程序设计", "公共基础课"),
]


class SchoolReportTools(ChatTools):
    """Serves a school report with Decimal credits, gaps, and a school-passed course."""

    def __init__(self, gaps: dict[str, str]):
        super().__init__()
        self._gaps = gaps

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        if tool == "getSchoolProgress":
            from agent_runtime.api.schemas import SchoolProgressImportResult

            nodes = [
                {
                    "nodeId": f"node:{index}",
                    "parentId": None,
                    "schoolNodeId": None,
                    "leaf": True,
                    "name": name,
                    "requiredCredits": 40,
                    "earnedCredits": 40 - int(remaining),
                    "remainingCredits": int(remaining),
                }
                for index, (name, remaining) in enumerate(self._gaps.items())
            ]
            return SchoolProgressImportResult.model_validate(
                {
                    "receipt": {
                        "schoolProgressId": "progress:1",
                        "contentHash": "c" * 64,
                        "importedAt": datetime.now(UTC).isoformat(),
                        "reused": True,
                    },
                    "snapshot": {
                        "format": "coursepilot-shu-academic-progress",
                        "version": 1,
                        "capturedAt": datetime.now(UTC).isoformat(),
                        "source": "browser adapter",
                        "nodes": nodes,
                        "courses": [
                            {
                                "nodeId": "node:0",
                                "courseCode": "CS205",
                                "name": "数据结构",
                                "credits": 3,
                                "outcome": "PASSED",
                                "completedYear": None,
                                "completedTerm": None,
                                "grade": None,
                                "makeup": None,
                                "retake": None,
                                "suggestedYear": None,
                                "suggestedTerm": None,
                            }
                        ],
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
        if tool == "listCourses":
            return list(CATALOG)
        return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)


class RawModel:
    """Returns exactly the given reply, to exercise lenient validation."""

    def __init__(self, courses=(), suggestions=(), reply="回答已生成。", question=None):
        self.calls = 0
        self.messages = []
        self._reply = AdviceChatModelReply(
            reply=reply,
            question=question,
            courses=list(courses),
            suggestions=list(suggestions),
            input_tokens=10,
            output_tokens=8,
        )

    def generate_chat(self, *, context, messages):
        self.calls += 1
        self.messages = messages
        return self._reply


def _model_facts(model) -> dict:
    return json.loads(model.messages[-1]["content"])


def test_school_report_with_decimal_credits_produces_answer_and_gap_facts():
    tools = SchoolReportTools({"学科基础课": "34", "专业选修课": "17", "公共基础课": "0"})
    model = ChatModel("CS201")
    answer = AdviceChatService(tool_client=tools, model_adapter=model).run(_request(), _context())

    facts = _model_facts(model)
    assert facts["schoolReportGaps"] == [
        {"category": "学科基础课", "remainingCredits": "34"},
        {"category": "专业选修课", "remainingCredits": "17"},
    ]
    listed = {item["courseCode"] for item in facts["availableCourses"]}
    # Gap categories join the default scope; the school-passed course and 公共基础课 stay out.
    assert listed == {"CS201", "CS301", "CS302", "CS303"}
    assert [item.courseCode for item in answer.courses] == ["CS201"]
    assert answer.schoolProgress is not None


def test_school_passed_course_is_excluded_even_without_java_record_entry():
    tools = SchoolReportTools({"学科基础课": "34"})
    model = ChatModel("CS301")
    AdviceChatService(tool_client=tools, model_adapter=model).run(_request(), _context())
    listed = {item["courseCode"] for item in _model_facts(model)["availableCourses"]}
    assert "CS205" not in listed


def test_short_vague_question_with_school_report_still_answers():
    tools = SchoolReportTools({"学科基础课": "34", "专业选修课": "17"})
    request = _request().model_copy(update={"message": "人工智能？", "interestText": ""})
    answer = AdviceChatService(tool_client=tools, model_adapter=FakeModelAdapter()).run(
        request, _context()
    )
    assert answer.reply
    assert answer.courses
    assert all(item.courseCode != "CS205" for item in answer.courses)


def test_invalid_suggestions_are_dropped_and_valid_ones_kept():
    tools = SchoolReportTools({"专业选修课": "17"})
    model = RawModel(
        courses=[{"courseCode": "CS301", "reason": "与人工智能相关。", "reviewNoteIds": []}],
        suggestions=[
            {"kind": "INTEREST", "label": "补充兴趣", "value": "机器人方向"},
            {"kind": "SELECT_COURSE", "label": "不存在", "value": "CS999"},
            {"kind": "PREFER_COURSE", "label": "加入偏好", "value": "CS301"},
        ],
    )
    answer = AdviceChatService(tool_client=tools, model_adapter=model).run(_request(), _context())
    assert [(s.kind, s.value) for s in answer.suggestions] == [
        ("INTEREST", "机器人方向"),
        ("PREFER_COURSE", "CS301"),
    ]
    assert any(issue.code == "MODEL_CITATION_DROPPED" for issue in answer.unknowns)
