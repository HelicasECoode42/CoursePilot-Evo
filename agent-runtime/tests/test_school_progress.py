from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agent_runtime.api.app import create_app
from agent_runtime.api.schemas.academic import AcademicRecord
from agent_runtime.api.schemas.school_progress import (
    SchoolProgressImportResult,
    SchoolProgressReceipt,
)
from agent_runtime.api.settings import Settings


class SchoolProgressTools:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        assert tool == "importSchoolProgress"
        assert context.subject_id
        assert idempotency_key == "school-key-1"
        self.calls += 1
        return SchoolProgressImportResult(
            receipt=SchoolProgressReceipt(
                schoolProgressId="school:demo",
                contentHash="a" * 64,
                importedAt=datetime.now(UTC),
                reused=False,
            ),
            snapshot=dto.snapshot,
            academicRecord=AcademicRecord(
                academicRecordId="record:demo",
                revision=1,
                curriculumSnapshotId=dto.curriculumSnapshotId,
                completedCourses=[],
                transcriptComplete=False,
                sourceKind="USER_IMPORT",
                createdAt=datetime.now(UTC),
            ),
        )


def _body() -> dict:
    return {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": "curr:demo",
        "snapshot": {
            "format": "coursepilot-shu-academic-progress",
            "version": 1,
            "capturedAt": "2026-10-29T00:00:00Z",
            "source": "fictional fixture",
            "nodes": [
                {
                    "nodeId": "node:parent",
                    "parentId": None,
                    "schoolNodeId": "98",
                    "leaf": False,
                    "name": "公共基础课",
                    "requiredCredits": 12,
                    "earnedCredits": 6,
                    "remainingCredits": 6,
                },
                {
                    "nodeId": "node:child",
                    "parentId": "node:parent",
                    "schoolNodeId": "54",
                    "leaf": True,
                    "name": "公共基础课",
                    "requiredCredits": 4,
                    "earnedCredits": 2,
                    "remainingCredits": 2,
                },
            ],
            "courses": [
                {
                    "nodeId": "node:child",
                    "courseCode": "CS001",
                    "name": "示例课程",
                    "credits": 2,
                    "outcome": "UNKNOWN",
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
    }


def test_import_requires_session_and_persists_before_success() -> None:
    tools = SchoolProgressTools()
    app = create_app(Settings(), tool_client=tools)
    client = TestClient(app)
    token = client.post("/api/v1/sessions").json()["data"]["sessionToken"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "school-key-1",
        "X-Request-Id": "req:school1",
    }

    missing_auth = client.put("/api/v1/school-progress", json=_body())
    assert missing_auth.status_code == 401

    response = client.put("/api/v1/school-progress", json=_body(), headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["academicRecord"]["sourceKind"] == "USER_IMPORT"
    assert response.json()["data"]["receipt"]["contentHash"] == "a" * 64
    replay = client.put("/api/v1/school-progress", json=_body(), headers=headers)
    assert replay.json() == response.json()
    assert tools.calls == 1

    changed = _body()
    changed["snapshot"]["nodes"][1]["remainingCredits"] = 1
    conflict = client.put("/api/v1/school-progress", json=changed, headers=headers)
    assert conflict.status_code == 409
    assert tools.calls == 1


def test_import_rejects_unknown_fields_and_invalid_outcome() -> None:
    client = TestClient(create_app(Settings(), tool_client=SchoolProgressTools()))
    token = client.post("/api/v1/sessions").json()["data"]["sessionToken"]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "school-key-1"}
    body = _body()
    body["snapshot"]["nodes"][1]["nodeId"] = "node:parent"
    response = client.put("/api/v1/school-progress", json=body, headers=headers)
    assert response.status_code == 422

    body = _body()
    body["snapshot"]["courses"][0]["outcome"] = "GUESSED_PASSED"
    response = client.put("/api/v1/school-progress", json=body, headers=headers)
    assert response.status_code == 422
