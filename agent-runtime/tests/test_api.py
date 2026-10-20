from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.model_client import (
    ModelConfigError,
    ModelInvalidOutput,
    ModelTimeout,
    ModelUpstreamError,
)
from agent_runtime.adapters.tool_client import ToolUnavailable
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import AcademicRecord, AuditResult, PlanningRequest
from agent_runtime.api.settings import Settings, load_settings
from agent_runtime.application.ids import digest
from agent_runtime.application.runner import PlanningRunner

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


class FakeToolClient:
    """Test double: returns fixed (clearly-fake) data per tool."""

    def call(self, tool: str, dto, context, *, params=None):
        if tool == "auditRequirements":
            return AuditResult(
                curriculumSnapshotId=dto.curriculumSnapshotId,
                academicRecordId=dto.academicRecordId,
                recordRevision=1,
                transcriptComplete=False,
                requirements=[],
                suggestedCourseCodes=[],
                unknowns=[],
            )
        if tool == "createAcademicRecord":
            return AcademicRecord(
                academicRecordId="record:demo",
                revision=1,
                curriculumSnapshotId=dto.curriculumSnapshotId,
                completedCourses=dto.completedCourses,
                transcriptComplete=dto.transcriptComplete,
                sourceKind=dto.sourceKind,
                createdAt=datetime.now(UTC),
            )
        if tool == "getAcademicRecord":
            return AcademicRecord(
                academicRecordId="record:demo",
                revision=1,
                curriculumSnapshotId="curr:demo",
                completedCourses=[],
                transcriptComplete=False,
                sourceKind="SYNTHETIC",
                createdAt=datetime.now(UTC),
            )
        if tool in {
            "listCurricula",
            "listCourses",
            "listTeacherCourseOptions",
            "searchReviews",
            "listCareerDirections",
            "listAcademicRecords",
        }:
            return []
        raise ToolUnavailable(tool)


def _request_body() -> dict:
    return json.loads(
        (CONTRACTS / "examples" / "planning-request.json").read_text(encoding="utf-8")
    )


def _record_body() -> dict:
    return {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": "curr:demo",
        "completedCourses": [],
        "transcriptComplete": False,
        "sourceKind": "SYNTHETIC",
    }


def _token(client: TestClient) -> str:
    return client.post("/api/v1/sessions").json()["data"]["sessionToken"]


def test_create_session() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/sessions")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "OK"
    assert body["data"]["sessionToken"]


def test_planning_requires_auth() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={"Idempotency-Key": "k1", "X-Request-Id": "req:x1"},
    )
    assert response.status_code == 401
    assert response.json()["status"] == "UNAUTHORIZED"


def test_planning_without_java_returns_503() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {_token(client)}",
            "Idempotency-Key": "k1",
            "X-Request-Id": "req:x1",
        },
    )
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "ERROR"
    assert body["issues"][0]["code"] == "TOOL_UNAVAILABLE"


def test_gateway_list_courses_ok_with_fake_java() -> None:
    client = TestClient(create_app(tool_client=FakeToolClient()))
    response = client.get(
        "/api/v1/courses",
        params={"curriculumSnapshotId": "curr:demo"},
        headers={"Authorization": f"Bearer {_token(client)}", "X-Request-Id": "req:x1"},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"items": [], "nextCursor": None}


def test_academic_records_requires_auth() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/academic-records",
        json=_record_body(),
        headers={"Idempotency-Key": "k1", "X-Request-Id": "req:x1"},
    )
    assert response.status_code == 401


def test_academic_records_save_is_idempotent() -> None:
    client = TestClient(create_app(tool_client=FakeToolClient()))
    headers = {
        "Authorization": f"Bearer {_token(client)}",
        "Idempotency-Key": "k1",
        "X-Request-Id": "req:x1",
    }
    first = client.post("/api/v1/academic-records", json=_record_body(), headers=headers)
    second = client.post("/api/v1/academic-records", json=_record_body(), headers=headers)
    assert first.status_code == 201
    assert first.json()["data"]["academicRecordId"] == "record:demo"
    assert second.json() == first.json()


def test_academic_records_list_requires_auth() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/academic-records", headers={"X-Request-Id": "req:x1"})
    assert response.status_code == 401


def test_academic_records_list_ok_with_fake_java() -> None:
    client = TestClient(create_app(tool_client=FakeToolClient()))
    headers = {"Authorization": f"Bearer {_token(client)}", "X-Request-Id": "req:x1"}
    response = client.get("/api/v1/academic-records", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == {"items": []}


def test_academic_records_read_uses_camel_case_path() -> None:
    client = TestClient(create_app(tool_client=FakeToolClient()))
    headers = {"Authorization": f"Bearer {_token(client)}", "X-Request-Id": "req:x1"}
    response = client.get("/api/v1/academic-records/record:demo", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["academicRecordId"] == "record:demo"


def test_planning_w2_fake_tools_returns_unknown_course_layer() -> None:
    client = TestClient(create_app(tool_client=TypedFakeToolClient()))
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {_token(client)}",
            "Idempotency-Key": "k-w2",
            "X-Request-Id": "req:w2",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["data"]["decision"] == "RECOMMENDATIONS"
    verification = body["data"]["recommendations"][0]["verification"]
    assert verification["verdict"] == "UNKNOWN"
    assert any(issue["code"] == "FAKE_MODEL" for issue in body["data"]["unknowns"])
    assert all(issue["code"] != "FAKE_MODEL" for issue in verification["unknownChecks"])


def test_planning_empty_catalog_is_unable_to_verify_not_422() -> None:
    client = TestClient(create_app(tool_client=FakeToolClient()))
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {_token(client)}",
            "Idempotency-Key": "k-empty",
            "X-Request-Id": "req:empty",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["data"]["decision"] == "UNABLE_TO_VERIFY"
    assert body["data"]["recommendations"] == []
    assert any(issue["code"] == "EVIDENCE_MISMATCH" for issue in body["data"]["unknowns"])
    assert any(issue["code"] == "FAKE_MODEL" for issue in body["data"]["unknowns"])
    assert body["issues"] == []


def test_planning_invalid_model_output_returns_422() -> None:
    class AlwaysInvalid:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            raise ModelInvalidOutput("broken json")

    app = create_app(tool_client=TypedFakeToolClient())
    app.state.runner = PlanningRunner(
        tool_client=app.state.tool_client,
        harness=app.state.harness,
        model_adapter=AlwaysInvalid(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {_token(client)}",
            "Idempotency-Key": "k-invalid",
            "X-Request-Id": "req:invalid",
        },
    )
    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "MODEL_INVALID_OUTPUT"
    assert response.json()["issues"][0]["retryable"] is False


def test_planning_model_rate_limit_returns_429() -> None:
    class Limited:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            raise ModelUpstreamError("模型端点限流", status_code=429)

    app = create_app(tool_client=TypedFakeToolClient())
    app.state.runner = PlanningRunner(
        tool_client=app.state.tool_client,
        harness=app.state.harness,
        model_adapter=Limited(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {_token(client)}",
            "Idempotency-Key": "k-rate",
            "X-Request-Id": "req:rate",
        },
    )
    assert response.status_code == 429
    issue = response.json()["issues"][0]
    assert issue["code"] == "MODEL_RATE_LIMITED"
    assert issue["retryable"] is True


def test_planning_model_unavailable_returns_503() -> None:
    class Down:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            raise ModelUpstreamError("模型端点不可用", status_code=503)

    app = create_app(tool_client=TypedFakeToolClient())
    app.state.runner = PlanningRunner(
        tool_client=app.state.tool_client,
        harness=app.state.harness,
        model_adapter=Down(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {_token(client)}",
            "Idempotency-Key": "k-down",
            "X-Request-Id": "req:down",
        },
    )
    assert response.status_code == 503
    issue = response.json()["issues"][0]
    assert issue["code"] == "MODEL_UNAVAILABLE"
    assert issue["retryable"] is True


def test_create_app_rejects_placeholder_model_when_endpoint_is_configured() -> None:
    with pytest.raises(ModelConfigError):
        create_app(
            Settings(
                model_base_url="https://api.deepseek.com",
                model_api_key="test-key",
                model_id="DEPLOYMENT_MODEL_PLACEHOLDER",
            )
        )


def test_planning_model_timeout_returns_504() -> None:
    class TimedOut:
        def generate(self, *, context, messages, tool_schemas):
            del context, messages, tool_schemas
            raise ModelTimeout("模型请求超时")

    app = create_app(tool_client=TypedFakeToolClient())
    app.state.runner = PlanningRunner(
        tool_client=app.state.tool_client,
        harness=app.state.harness,
        model_adapter=TimedOut(),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {_token(client)}",
            "Idempotency-Key": "k-timeout",
            "X-Request-Id": "req:timeout",
        },
    )
    assert response.status_code == 504
    assert response.json()["issues"][0]["code"] == "MODEL_TIMEOUT"
    assert response.json()["issues"][0]["retryable"] is True


def test_planning_in_progress_same_key_returns_409() -> None:
    app = create_app(tool_client=TypedFakeToolClient())
    client = TestClient(app)
    token = _token(client)
    payload = PlanningRequest.model_validate(_request_body())
    body_digest = digest(
        json.dumps(payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    )
    session_id = app.state.session_store.resolve(token)
    app.state.idempotency.begin(session_id, "planning", "k-inflight", body_digest)
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "k-inflight",
            "X-Request-Id": "req:inflight",
        },
    )
    assert response.status_code == 409
    assert response.json()["issues"][0]["code"] == "REQUEST_IN_PROGRESS"


def test_plain_settings_ignores_local_env_file() -> None:
    settings = Settings()
    assert settings.use_fake_tools is False
    assert settings.model_api_key == ""
    assert settings.java_base_url is None


def test_load_settings_reads_explicit_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CP_USE_FAKE_TOOLS=true\nCP_MODEL_ID=deepseek-chat\n", encoding="utf-8")
    settings = load_settings(env_file)
    assert settings.use_fake_tools is True
    assert settings.model_id == "deepseek-chat"
    assert settings.model_api_key == ""


def test_reports_requires_admin_key() -> None:
    client = TestClient(create_app(Settings(admin_key="secret")))
    headers = {"Authorization": f"Bearer {_token(client)}", "X-Request-Id": "req:x1"}
    without_admin = client.get("/api/v1/reports/runs/run:demo", headers=headers)
    assert without_admin.status_code == 403
    with_admin = client.get(
        "/api/v1/reports/runs/run:demo", headers={**headers, "X-Admin-Key": "secret"}
    )
    assert with_admin.status_code == 404
