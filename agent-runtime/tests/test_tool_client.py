from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agent_runtime.adapters.tool_client import InvalidTool, ToolClient, ToolUnavailable
from agent_runtime.api.schemas import AuditRequest
from agent_runtime.application.context import ExecutionContext


def _context() -> ExecutionContext:
    return ExecutionContext(
        subject_id="subject:demo",
        request_id="req:demo",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id=None,
        model_id="m",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=20),
        harness_version="harness:v0",
    )


def test_unknown_tool_is_rejected() -> None:
    client = ToolClient("http://java.test", "svc")
    with pytest.raises(InvalidTool):
        client.call("dropTable", None, _context())


def test_missing_base_url_is_unavailable() -> None:
    client = ToolClient(None, "svc")
    with pytest.raises(ToolUnavailable):
        client.call("listCourses", None, _context())


def test_get_list_parses_envelope_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Service-Key"] == "svc"
        assert request.headers["X-Subject-Id"] == "subject:demo"
        assert request.headers["X-Request-Id"] == "req:demo"
        assert request.url.params["curriculumSnapshotId"] == "curr:demo"
        return httpx.Response(
            200,
            json={
                "schemaVersion": "1.0",
                "requestId": "req:demo",
                "traceId": None,
                "status": "OK",
                "data": {
                    "items": [
                        {
                            "courseCode": "CS101",
                            "name": "程序设计",
                            "credits": "4.00",
                            "category": "必修",
                            "sourceRefIds": ["source:x"],
                        }
                    ]
                },
                "provenance": [],
                "issues": [],
            },
        )

    client = ToolClient("http://java.test", "svc", transport=httpx.MockTransport(handler))
    courses = client.call(
        "listCourses", None, _context(), params={"curriculumSnapshotId": "curr:demo"}
    )
    assert courses[0].courseCode == "CS101"


def test_get_path_param_uses_camel_case() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/v1/academic-records/record:demo")
        return httpx.Response(
            200,
            json={
                "schemaVersion": "1.0",
                "requestId": "req:demo",
                "traceId": None,
                "status": "OK",
                "data": {
                    "academicRecordId": "record:demo",
                    "revision": 1,
                    "curriculumSnapshotId": "curr:demo",
                    "completedCourses": [],
                    "transcriptComplete": False,
                    "sourceKind": "SYNTHETIC",
                    "createdAt": "2026-10-14T00:00:00Z",
                },
                "provenance": [],
                "issues": [],
            },
        )

    client = ToolClient("http://java.test", "svc", transport=httpx.MockTransport(handler))
    record = client.call("getAcademicRecord", None, _context(), params={"recordId": "record:demo"})
    assert record.academicRecordId == "record:demo"


def test_post_sends_dto_and_parses_audit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b"curr:demo" in body
        return httpx.Response(
            200,
            json={
                "schemaVersion": "1.0",
                "requestId": "req:demo",
                "traceId": None,
                "status": "OK",
                "data": {
                    "curriculumSnapshotId": "curr:demo",
                    "academicRecordId": "record:demo",
                    "recordRevision": 1,
                    "transcriptComplete": False,
                    "requirements": [],
                    "suggestedCourseCodes": ["CS101"],
                    "unknowns": [],
                },
                "provenance": [],
                "issues": [],
            },
        )

    client = ToolClient("http://java.test", "svc", transport=httpx.MockTransport(handler))
    result = client.call(
        "auditRequirements",
        AuditRequest(
            schemaVersion="1.0",
            curriculumSnapshotId="curr:demo",
            academicRecordId="record:demo",
        ),
        _context(),
    )
    assert result.suggestedCourseCodes == ["CS101"]


def test_http_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "ERROR"})

    client = ToolClient("http://java.test", "svc", transport=httpx.MockTransport(handler))
    with pytest.raises(ToolUnavailable):
        client.call("listCourses", None, _context())
