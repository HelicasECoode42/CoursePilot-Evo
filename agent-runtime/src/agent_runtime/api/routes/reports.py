"""GET /api/v1/reports/runs/{runId} — restricted teacher report."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header

from agent_runtime.api.deps import require_admin, require_subject
from agent_runtime.api.errors import NotFoundError

router = APIRouter()


@router.get("/api/v1/reports/runs/{runId}")
def get_run_report(
    runId: str,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    admin: Annotated[None, Depends(require_admin)],
) -> dict:
    # W4/W5: read the aggregated report from the run store (benchmark module D).
    # No runs exist yet, so this is honestly NOT_FOUND.
    raise NotFoundError("报告不存在")
