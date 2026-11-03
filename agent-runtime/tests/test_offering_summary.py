"""POST /api/v1/offering-summary: batched section counts with fake Java tools."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agent_runtime.adapters.tool_client import ToolRejected
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import CourseOffering, Meeting
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.offering_summary import summarize_offerings


def _row(course: str, class_id: str, teacher: str = "甲") -> CourseOffering:
    return CourseOffering(
        courseCode=course,
        classId=class_id,
        teacherKey=None,
        teacherText=teacher,
        credits=None,
        capacity=None,
        meetingTextRaw="演示",
        meetings=[Meeting(dayOfWeek=1, sectionStart=1, sectionEnd=2, weeks=[1])],
        parseStatus="PARSED",
        sourceRefId="source:demo",
    )


class _Java:
    """Fake listOfferings: ``rows`` is the snapshot, ``extra`` pads it to a full page."""

    def __init__(self, rows, *, extra: int = 0, fail: set[str] | None = None) -> None:
        self._rows = list(rows)
        self._extra = extra
        self._fail = fail or set()
        self.calls: list[str | None] = []

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        assert tool == "listOfferings"
        code = params.get("courseCode")
        self.calls.append(code)
        if code is None:
            pad = [_row(f"FILL{i:03d}", f"c{i}") for i in range(self._extra)]
            return (self._rows + pad)[: params["limit"]]
        if code in self._fail:
            raise ToolRejected(tool, 503, "UNAVAILABLE", "down")
        return [row for row in self._rows if row.courseCode == code]


def _context() -> ExecutionContext:
    return ExecutionContext(
        subject_id="subject:demo",
        request_id="req:demo",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id="offer:demo",
        model_id="none",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=30),
        harness_version="harness:v0",
    )


def _run(java: _Java, codes: list[str]):
    return summarize_offerings(
        java,
        _context(),
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id="offer:demo",
        course_codes=codes,
    )


def test_short_page_settles_all_courses_with_one_call() -> None:
    java = _Java([_row("CS101", "a", "甲"), _row("CS101", "b", "乙"), _row("MA201", "c")])
    result = _run(java, ["CS101", "MA201", "PH101"])

    assert java.calls == [None]
    counts = {item.courseCode: item.sectionCount for item in result.items}
    assert counts == {"CS101": 2, "MA201": 1, "PH101": 0}
    cs = next(item for item in result.items if item.courseCode == "CS101")
    assert cs.teacherTexts == ("甲", "乙")
    assert result.unknown_course_codes == []


def test_full_page_falls_back_to_one_lookup_per_course() -> None:
    java = _Java([_row("CS101", "a")], extra=200)
    result = _run(java, ["CS101", "PH101"])

    assert java.calls == [None, "CS101", "PH101"]
    assert {item.courseCode: item.sectionCount for item in result.items} == {
        "CS101": 1,
        "PH101": 0,
    }


def test_failed_lookup_is_unknown_not_zero() -> None:
    java = _Java([_row("CS101", "a")], extra=200, fail={"MA201"})
    result = _run(java, ["CS101", "MA201"])

    assert result.unknown_course_codes == ["MA201"]
    assert [item.courseCode for item in result.items] == ["CS101"]


def test_duplicate_codes_are_answered_once() -> None:
    java = _Java([_row("CS101", "a")])
    result = _run(java, ["CS101", "CS101"])
    assert [item.courseCode for item in result.items] == ["CS101"]


def test_api_returns_envelope_with_counts_and_rejects_too_many_codes() -> None:
    class _Fake:
        def call(self, tool, dto, context, *, params=None, idempotency_key=None):
            return [_row("CS101", "a")]

    client = TestClient(create_app(tool_client=_Fake()))
    token = client.post("/api/v1/sessions").json()["data"]["sessionToken"]
    headers = {"Authorization": f"Bearer {token}", "X-Request-Id": "req:summary"}
    body = {
        "curriculumSnapshotId": "curr:demo",
        "offeringSnapshotId": "offer:demo",
        "courseCodes": ["CS101", "PH101"],
    }
    response = client.post("/api/v1/offering-summary", json=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert data["data"]["items"][0] == {
        "courseCode": "CS101",
        "sectionCount": 1,
        "teacherTexts": ["甲"],
    }
    assert data["data"]["items"][1] == {
        "courseCode": "PH101",
        "sectionCount": 0,
        "teacherTexts": [],
    }

    too_many = dict(body, courseCodes=[f"C{i:03d}" for i in range(11)])
    rejected = client.post("/api/v1/offering-summary", json=too_many, headers=headers)
    # Body validation is 422 across the gateway (see test_api.py).
    assert rejected.status_code == 422
