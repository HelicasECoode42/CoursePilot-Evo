from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessLoader
from agent_runtime.adapters.model_client import ModelInvalidOutput
from agent_runtime.adapters.result_repository import FileResultRepository
from agent_runtime.adapters.tool_client import ToolRejected
from agent_runtime.api.app import create_app
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.settings import Settings
from agent_runtime.application.budget import Budget
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.run_manifest import build_run_manifest
from agent_runtime.application.runner import PlanningRunner


def test_run_manifest_uses_configured_budget_values() -> None:
    context = ExecutionContext(
        subject_id="session:test",
        request_id="req:test",
        curriculum_snapshot_id="curr:test",
        offering_snapshot_id=None,
        model_id="model:test",
        temperature=0,
        deadline=datetime.now(UTC),
        harness_version="harness:test",
    )
    manifest = build_run_manifest(
        context=context,
        budget=Budget(
            max_input_tokens=3000,
            max_output_tokens=1200,
            max_tool_calls=4,
            max_model_calls=2,
            deadline_ms=2500,
        ),
    )
    assert (manifest.maxInputTokens, manifest.maxOutputTokens) == (3000, 1200)
    assert (manifest.maxToolCalls, manifest.maxModelCalls, manifest.deadlineMs) == (4, 2, 2500)


def test_paid_model_failure_is_charged_and_replayed_for_same_key(tmp_path: Path) -> None:
    calls = 0

    class PaidFailure:
        def generate(self, *, context, messages):
            nonlocal calls
            del context, messages
            calls += 1
            raise ModelInvalidOutput(
                "provider returned invalid output", input_tokens=17, output_tokens=9
            )

    app = create_app(
        Settings(use_fake_tools=False, deadline_ms=2500),
        tool_client=TypedFakeToolClient(),
    )
    app.state.runner = PlanningRunner(
        tool_client=app.state.tool_client,
        harness=app.state.harness,
        model_adapter=PaidFailure(),
        result_repository=FileResultRepository(tmp_path),
    )
    client = TestClient(app)
    token = client.post("/api/v1/sessions").json()["data"]["sessionToken"]
    request = json.loads(
        (
            Path(__file__).resolve().parents[2] / "contracts/examples/planning-request.json"
        ).read_text(encoding="utf-8")
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "paid-failure",
        "X-Request-Id": "req:paid-failure",
    }
    first = client.post("/api/v1/planning", json=request, headers=headers)
    second = client.post("/api/v1/planning", json=request, headers=headers)
    session_id = app.state.session_store.resolve(token)
    assert first.status_code == second.status_code == 422
    assert calls == 1
    assert app.state.spend_ledger.spent(session_id) == (17, 9)
    trace_dirs = list(tmp_path.iterdir())
    assert len(trace_dirs) == 1
    assert (trace_dirs[0] / "failure.json").exists()
    events = [
        json.loads(line)
        for line in (trace_dirs[0] / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["eventType"] == "ERROR"


def test_configured_deadline_is_used_for_planning_context() -> None:
    seen: list[ExecutionContext] = []

    class CapturingRunner:
        def run(self, body, context):
            seen.append(context)
            raise ModelInvalidOutput("stop before answer")

    app = create_app(
        Settings(deadline_ms=2500),
        tool_client=TypedFakeToolClient(),
        runner=CapturingRunner(),
    )
    client = TestClient(app)
    token = client.post("/api/v1/sessions").json()["data"]["sessionToken"]
    request = json.loads(
        (
            Path(__file__).resolve().parents[2] / "contracts/examples/planning-request.json"
        ).read_text(encoding="utf-8")
    )
    client.post(
        "/api/v1/planning",
        json=request,
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "deadline",
            "X-Request-Id": "req:deadline",
        },
    )
    assert len(seen) == 1
    assert 0 < (seen[0].deadline - datetime.now(UTC)).total_seconds() <= 2.5


def test_failure_archive_errors_do_not_replace_original_save_error() -> None:
    class BrokenRepository:
        failure_attempts = 0

        def save(self, **kwargs):
            del kwargs
            raise OSError("answer save failed")

        def save_failure(self, **kwargs):
            del kwargs
            self.failure_attempts += 1
            raise OSError("failure save failed")

    request_data = json.loads(
        (
            Path(__file__).resolve().parents[2] / "contracts/examples/planning-request.json"
        ).read_text(encoding="utf-8")
    )
    from agent_runtime.api.schemas import PlanningRequest

    request = PlanningRequest.model_validate(request_data)
    request = request.model_copy(
        update={
            "intent": request.intent.model_copy(
                update={"motives": [], "priorityOrder": [], "hardConstraints": []}
            )
        }
    )
    context = ExecutionContext(
        subject_id="session:test",
        request_id="req:test",
        curriculum_snapshot_id=request.curriculumSnapshotId,
        offering_snapshot_id=request.offeringSnapshotId,
        model_id="model:test",
        temperature=0,
        deadline=datetime.now(UTC),
        harness_version="harness:test",
    )
    repository = BrokenRepository()
    runner = PlanningRunner(
        tool_client=TypedFakeToolClient(),
        harness=HarnessLoader(Path(__file__).resolve().parents[1] / "harness").load(),
        result_repository=repository,
    )
    with pytest.raises(OSError, match="answer save failed") as caught:
        runner.run(request, context)
    assert repository.failure_attempts == 1
    assert caught.value.__notes__ == ["Failed to persist the failed-run record"]


def test_paid_verifier_rejection_replays_without_reconstructing_exception() -> None:
    store = IdempotencyStore()
    failure = ToolRejected("validatePlan", 409, "SNAPSHOT_MISMATCH", "changed snapshot")
    failure.input_tokens = 17

    def reject() -> dict:
        raise failure

    with pytest.raises(ToolRejected):
        store.run("session:one", "planning", "key", "body", reject, cache_failure=lambda _: True)

    with pytest.raises(ToolRejected) as replay:
        store.run("session:one", "planning", "key", "body", lambda: {})
    assert replay.value is not failure
    assert (replay.value.status_code, replay.value.issue_code, replay.value.input_tokens) == (
        409,
        "SNAPSHOT_MISMATCH",
        17,
    )
