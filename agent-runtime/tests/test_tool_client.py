from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.tool_client import (
    InvalidTool,
    ToolClient,
    ToolContractViolation,
    ToolPage,
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
                            "credits": 4.0,
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


def test_get_list_page_preserves_next_cursor() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_envelope("OK", {"items": [], "nextCursor": "20"}),
        )

    page = _client(handler).call_page("listTeacherCourseOptions", None, _context())
    assert isinstance(page, ToolPage)
    assert page.items == []
    assert page.next_cursor == "20"


@pytest.mark.parametrize(
    "data",
    [
        {"items": []},
        {"items": [], "nextCursor": 20},
    ],
    ids=["missing-cursor", "non-string-cursor"],
)
def test_get_list_page_rejects_invalid_cursor_shape(data: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_envelope("OK", data))

    with pytest.raises(ToolContractViolation, match="nextCursor"):
        _client(handler).call_page("listTeacherCourseOptions", None, _context())


@pytest.mark.parametrize("cursor", ["-1", "1x", "1234567890"])
def test_typed_fake_tools_reject_invalid_cursor_like_java(cursor: str) -> None:
    with pytest.raises(ToolRejected) as caught:
        TypedFakeToolClient().call_page("listCourses", None, _context(), params={"cursor": cursor})
    assert caught.value.status_code == 400
    assert caught.value.issue_code == "INVALID_QUERY"


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


def test_plan_tool_request_serializes_max_credits_as_json_number() -> None:
    import json
    from decimal import Decimal

    from agent_runtime.api.schemas import PlanValidationRequest

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        credit_limit = body["hardConstraints"][0]["value"]
        assert isinstance(credit_limit, (int, float)) and not isinstance(credit_limit, bool)
        assert credit_limit == 12.5
        return httpx.Response(
            200,
            json=_envelope(
                "UNKNOWN",
                {
                    "verifierResultId": "vr:credits",
                    "verdict": "UNKNOWN",
                    "scope": "SIMULATION",
                    "curriculumSnapshotId": "curr:demo",
                    "offeringSnapshotId": "offer:demo",
                    "recordRevision": 1,
                    "violations": [],
                    "unknownChecks": [],
                    "performedChecks": [],
                    "sourceRefIds": [],
                },
            ),
        )

    request = PlanValidationRequest(
        schemaVersion="1.0",
        curriculumSnapshotId="curr:demo",
        offeringSnapshotId="offer:demo",
        academicRecordId="subject:demo",
        mode="SIMULATION",
        items=[{"courseCode": "CS101", "teacherKey": None, "classId": None}],
        hardConstraints=[
            {
                "kind": "MAX_CREDITS",
                "courseCode": None,
                "teacherKey": None,
                "dayOfWeek": None,
                "section": None,
                "value": Decimal("12.50"),
                "sourceText": "最多12.5学分",
            }
        ],
    )
    result = _client(handler).call("validatePlan", request, _context())
    assert result.verdict == "UNKNOWN"


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
                            "credits": 4.0,
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


def test_get_retries_transient_error_once_within_budget() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("transient")
        return httpx.Response(200, json=_envelope("OK", {"items": []}))

    assert _client(handler).call("listCourses", None, _context()) == []
    assert calls == 2


def test_get_skips_retry_when_remaining_budget_is_too_small() -> None:
    """docs/04: a read-only retry must stay inside the time budget."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        time.sleep(0.15)
        raise httpx.ConnectError("transient")

    context = ExecutionContext(
        subject_id="subject:demo",
        request_id="req:demo",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id=None,
        model_id="m",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=0.2),
        harness_version="harness:v0",
    )
    with pytest.raises(ToolUnavailable):
        _client(handler).call("listCourses", None, context)
    # Only ~50 ms of the 200 ms budget is left after the first attempt: no retry.
    assert calls == 1


def test_java_business_rejections_are_not_reported_as_contract_violations() -> None:
    """Java 的 422/409 业务拒绝必须原样透出，不能变成 502。

    学生指了一个不存在的培养快照时，Java 返 422 SNAPSHOT_NOT_FOUND。原来任何非
    401/403/404/429 的 4xx 都落到 TOOL_CONTRACT_VIOLATION 502，于是页面显示的是
    「网关坏了」，而不是「没这个培养方案」。400 仍然算违约：那表示本服务把请求拼错了。
    """
    from agent_runtime.adapters.tool_client import ToolRejected
    from agent_runtime.api.errors import _rejected_response

    cases = {
        (422, "SNAPSHOT_NOT_FOUND"): (422, "INVALID_INPUT", "SNAPSHOT_NOT_FOUND"),
        (409, "SNAPSHOT_MISMATCH"): (409, "CONFLICT", "SNAPSHOT_MISMATCH"),
        (409, "CONFLICT"): (409, "CONFLICT", "CONFLICT"),
        (409, "SNAPSHOT_COURSE_FACTS_UNKNOWN"): (409, "CONFLICT", "SNAPSHOT_COURSE_FACTS_UNKNOWN"),
    }
    for (status, code), (want_status, want_envelope, want_code) in cases.items():
        got_status, got_envelope, issue = _rejected_response(
            ToolRejected("createAcademicRecord", status, code, "nope")
        )
        assert (got_status, got_envelope, issue.code) == (want_status, want_envelope, want_code)

    # 400 是本服务拼错了请求，仍然是违约。
    status, envelope_status, issue = _rejected_response(
        ToolRejected("createAcademicRecord", 400, "INVALID_INPUT", "bad field")
    )
    assert (status, envelope_status, issue.code) == (502, "ERROR", "TOOL_CONTRACT_VIOLATION")


def test_list_offering_snapshots_hits_offering_path_and_keeps_kind() -> None:
    # 开课快照走自己的路径，且 kind 原样保留：不能被当成培养方案返回。
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        item = {
            "snapshotId": "OFFER_2025_FALL",
            "kind": "OFFERING",
            "state": "PUBLISHED",
            "sourceKind": "SYNTHETIC",
            "termId": "2025-FALL",
            "createdAt": "2025-08-15T00:00:00Z",
            "sourceValidation": "SYNTHETIC",
        }
        return httpx.Response(200, json=_envelope("OK", {"items": [item]}))

    items = _client(handler).call("listOfferingSnapshots", None, _context())
    assert seen == ["/api/v1/offering-snapshots"]
    assert [i.kind for i in items] == ["OFFERING"]
    assert items[0].sourceValidation == "SYNTHETIC"
