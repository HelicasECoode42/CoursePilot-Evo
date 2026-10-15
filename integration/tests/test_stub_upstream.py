"""受控假响应的自测：钉住「可重复」「只答未知」「不编时间」与契约结构。

不联网、不依赖 C：在后台线程起受控服务，用真实 HTTP（标准库）打它。
"""

from __future__ import annotations

import json

import pytest

import stub_upstream
from stack_checks import UrllibTransport, envelope_problems
from stub_upstream import DEFAULT_REQUEST_ID, serve_in_thread

TRANSPORT = UrllibTransport()


@pytest.fixture
def stub(request, monkeypatch, tmp_path):
    monkeypatch.setattr(stub_upstream, "RECORD_DIR", tmp_path)
    scenario = getattr(request, "param", "degrade_unknown")
    server, url, _thread, state = serve_in_thread(scenario=scenario)
    yield url, state
    server.shutdown()


def token_for(url: str) -> str:
    response = TRANSPORT.request("POST", url + "/api/v1/sessions", {"X-Request-Id": DEFAULT_REQUEST_ID})
    return response.payload["data"]["sessionToken"]


def auth(url: str) -> dict:
    return {"X-Request-Id": DEFAULT_REQUEST_ID, "Authorization": "Bearer " + token_for(url)}


def test_stub_response_is_byte_identical_on_repeat(stub):
    url, _state = stub
    body = {"schemaVersion": "1.0", "curriculumSnapshotId": "cur-stub-2024-cs", "academicRecordId": "record-stub-1"}
    headers = auth(url) | {"Idempotency-Key": "k1"}
    first = TRANSPORT.request("POST", url + "/api/v1/planning", headers, body)
    second = TRANSPORT.request("POST", url + "/api/v1/planning", headers, body)
    assert first.raw == second.raw and first.status == second.status == 200


def test_default_scenario_refuses_to_recommend(stub):
    url, _state = stub
    response = TRANSPORT.request("POST", url + "/api/v1/planning", auth(url), {"schemaVersion": "1.0"})
    answer = response.payload["data"]
    assert answer["decision"] == "UNABLE_TO_VERIFY"
    assert answer["recommendations"] == []


@pytest.mark.parametrize("stub", ["normal"], indirect=True)
def test_normal_scenario_stays_course_only(stub):
    url, _state = stub
    response = TRANSPORT.request("POST", url + "/api/v1/planning", auth(url), {"schemaVersion": "1.0"})
    answer = response.payload["data"]
    assert answer["decision"] == "RECOMMENDATIONS"
    scopes = [item["verification"]["scope"] for item in answer["recommendations"]]
    assert scopes == ["COURSE_ONLY"]
    assert all(item["verification"]["offeringSnapshotId"] is None for item in answer["recommendations"])


@pytest.mark.parametrize("stub", ["tool_unavailable"], indirect=True)
def test_unavailable_scenario_reports_503(stub):
    url, _state = stub
    response = TRANSPORT.request("POST", url + "/api/v1/requirements/audit", auth(url), {"schemaVersion": "1.0"})
    assert response.status == 503
    assert response.envelope_status == "ERROR"
    assert "TOOL_UNAVAILABLE" in response.issue_codes


def test_every_response_is_a_contract_envelope(stub):
    url, _state = stub
    for method, path, headers, body in (
        ("POST", "/api/v1/sessions", {"X-Request-Id": DEFAULT_REQUEST_ID}, None),
        ("GET", "/api/v1/curriculum-snapshots", auth(url), None),
        ("GET", "/api/v1/nope", auth(url), None),
        ("GET", "/api/v1/curriculum-snapshots", {"X-Request-Id": DEFAULT_REQUEST_ID}, None),
    ):
        response = TRANSPORT.request(method, url + path, headers, body)
        assert envelope_problems(response) == [], f"{method} {path}"


def test_missing_bearer_is_401_and_unknown_route_is_404(stub):
    url, _state = stub
    unauthorized = TRANSPORT.request("GET", url + "/api/v1/curriculum-snapshots", {"X-Request-Id": DEFAULT_REQUEST_ID})
    assert unauthorized.status == 401 and unauthorized.envelope_status == "UNAUTHORIZED"
    missing = TRANSPORT.request("GET", url + "/api/v1/nope", auth(url))
    assert missing.status == 404 and missing.envelope_status == "NOT_FOUND"


def test_records_file_hashes_each_exchange(stub, tmp_path):
    url, _state = stub
    headers = auth(url)
    TRANSPORT.request("GET", url + "/api/v1/curriculum-snapshots", headers)
    TRANSPORT.request("GET", url + "/api/v1/curriculum-snapshots", headers)
    entries = [json.loads(line) for line in (tmp_path / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    same_path = [e for e in entries if e["path"] == "/api/v1/curriculum-snapshots"]
    assert len(same_path) == 2
    assert same_path[0]["requestSha256"] != "" and same_path[0]["responseSha256"] == same_path[1]["responseSha256"]


def test_snapshot_and_planning_answer_pass_the_domain_schema(stub):
    jsonschema = pytest.importorskip("jsonschema")
    from check_stub import schema_validator

    url, _state = stub
    validate_snapshot = schema_validator("SnapshotSummary")
    validate_answer = schema_validator("PlanningAnswer")
    assert validate_snapshot is not None and validate_answer is not None

    items = TRANSPORT.request("GET", url + "/api/v1/curriculum-snapshots", auth(url)).payload["data"]["items"]
    assert validate_snapshot(items[0]) == []
    answer = TRANSPORT.request("POST", url + "/api/v1/planning", auth(url), {"schemaVersion": "1.0"}).payload["data"]
    assert validate_answer(answer) == []
    assert jsonschema.__name__ == "jsonschema"
