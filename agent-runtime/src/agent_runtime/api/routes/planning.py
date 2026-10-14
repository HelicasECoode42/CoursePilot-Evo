"""POST /api/v1/planning — the single planning entry point."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from agent_runtime.api.deps import get_idempotency, get_runner, require_subject
from agent_runtime.api.errors import envelope
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.schemas import PlanningRequest
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import digest
from agent_runtime.application.runner import PlanningRunner

router = APIRouter()


@router.post("/api/v1/planning")
def plan(
    request: Request,
    body: PlanningRequest,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    runner: Annotated[PlanningRunner, Depends(get_runner)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency)],
) -> dict:
    body_digest = digest(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    )

    def produce() -> dict:
        settings = request.app.state.settings
        harness = request.app.state.harness
        context = ExecutionContext(
            subject_id=subject_id,
            request_id=x_request_id,
            curriculum_snapshot_id=body.curriculumSnapshotId,
            offering_snapshot_id=body.offeringSnapshotId,
            model_id=settings.model_id,
            temperature=settings.temperature,
            deadline=datetime.now(UTC) + timedelta(milliseconds=45000),
            harness_version=harness.version,
        )
        answer = runner.run(body, context)
        return envelope(x_request_id, "OK", answer).model_dump(mode="json")

    return idempotency.run(subject_id, "planning", idempotency_key, body_digest, produce)
