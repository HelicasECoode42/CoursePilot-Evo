from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from agent_runtime.adapters.tool_client import ToolUnavailable
from agent_runtime.api.app import create_app
from agent_runtime.api.schemas import AcademicRecord, AuditResult
from agent_runtime.api.settings import Settings

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


def test_reports_requires_admin_key() -> None:
    client = TestClient(create_app(Settings(admin_key="secret")))
    headers = {"Authorization": f"Bearer {_token(client)}", "X-Request-Id": "req:x1"}
    without_admin = client.get("/api/v1/reports/runs/run:demo", headers=headers)
    assert without_admin.status_code == 403
    with_admin = client.get(
        "/api/v1/reports/runs/run:demo", headers={**headers, "X-Admin-Key": "secret"}
    )
    assert with_admin.status_code == 404
