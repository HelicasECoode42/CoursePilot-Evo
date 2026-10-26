from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agent_runtime.adapters.tool_client import (
    InvalidTool,
    ToolClient,
    ToolContractViolation,
    ToolRejected,
    ToolUnavailable,
)
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


def _envelope(status: str, data: object, issues: list | None = None) -> dict:
    return {
        "schemaVersion": "1.0",
        "requestId": "req:demo",
        "traceId": None,
        "status": status,
        "data": data,
        "provenance": [],
        "issues": issues or [],
    }


def _client(handler) -> ToolClient:
    return ToolClient("http://java.test", "svc", transport=httpx.MockTransport(handler))


def test_contract_violation_is_not_reported_as_unavailable() -> None:
    """A provider that answers off-contract is a provider defect, not an outage.

    Regression: Pydantic's ValidationError subclasses ValueError, so the old
    ``except (ValueError, TypeError, KeyError)`` turned every contract break into
    TOOL_UNAVAILABLE. Measured against the real Java service, five of seven tools
    failed with that single indistinguishable error.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        # Course requires sourceRefIds (domain.schema.json); this one omits it.
        return httpx.Response(
            200,
            json=_envelope(
                "OK",
                {
                    "items": [
                        {
                            "courseCode": "CS101",
                            "name": "程序设计",
                            "credits": "4.00",
                            "category": "必修",
                        }
                    ]
                },
            ),
        )

    with pytest.raises(ToolContractViolation) as caught:
        _client(handler).call("listCourses", None, _context())
    assert "sourceRefIds" in str(caught.value)


def test_list_endpoint_without_items_is_a_contract_violation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope("OK", None))

    with pytest.raises(ToolContractViolation):
        _client(handler).call("listCourses", None, _context())


def test_null_data_on_single_object_is_a_contract_violation() -> None:
    # Java answers UNKNOWN with data=null for records it cannot assemble yet.
    # Validating None must say so, not look like the service died.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope("UNKNOWN", None))

    with pytest.raises(ToolContractViolation):
        _client(handler).call("getAcademicRecord", None, _context(), params={"recordId": "r"})


def test_bad_service_key_keeps_its_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json=_envelope(
                "ERROR",
                None,
                [{"code": "SERVICE_KEY_INVALID", "message": "缺少或错误的 X-Service-Key"}],
            ),
        )

    with pytest.raises(ToolRejected) as caught:
        _client(handler).call("listCourses", None, _context())
    assert caught.value.status_code == 401
    assert caught.value.issue_code == "SERVICE_KEY_INVALID"


def test_not_visible_keeps_its_404() -> None:
    # java.openapi.json defines 404 as "object not visible or absent". Flattening
    # it to 503 would hide an authorization outcome behind "dependency down".
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json=_envelope("ERROR", None, [{"code": "NOT_VISIBLE", "message": "不可见"}])
        )

    with pytest.raises(ToolRejected) as caught:
        _client(handler).call("getAcademicRecord", None, _context(), params={"recordId": "other"})
    assert caught.value.status_code == 404
    assert caught.value.issue_code == "NOT_VISIBLE"


def test_rejection_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json=_envelope("ERROR", None, [{"code": "X", "message": "y"}]))

    with pytest.raises(ToolRejected):
        _client(handler).call("listCourses", None, _context())
    assert len(calls) == 1, "密钥被拒不会因为重试而变对"


def test_server_error_is_still_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "ERROR"})

    with pytest.raises(ToolUnavailable):
        _client(handler).call("listCourses", None, _context())


def test_unknown_envelope_still_returns_data() -> None:
    # UNKNOWN means "this is as far as the facts go", not "the query failed".
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope("UNKNOWN", {"items": []}))

    assert _client(handler).call("listAcademicRecords", None, _context()) == []


def test_list_endpoint_with_bare_array_is_a_contract_violation() -> None:
    # The contract wants data to be an object with items. A bare array is not
    # a list shape the contract allows, so it must not be accepted as one.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope("OK", []))

    with pytest.raises(ToolContractViolation) as caught:
        _client(handler).call("listCourses", None, _context())
    assert "data.items" in str(caught.value)
