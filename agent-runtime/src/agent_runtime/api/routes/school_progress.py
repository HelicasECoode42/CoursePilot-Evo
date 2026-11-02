"""Persist a school progress snapshot through the Java fact service."""

from __future__ import annotations

import json
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Request

from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.deps import get_idempotency, get_tool_client, make_context, require_subject
from agent_runtime.api.errors import envelope
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.schemas.school_progress import (
    SchoolProgressImport,
    SchoolProgressImportResult,
)
from agent_runtime.application.ids import digest

router = APIRouter()


@router.put("/api/v1/school-progress")
def import_school_progress(
    request: Request,
    body: SchoolProgressImport,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency)],
) -> dict:
    normalized = body.model_dump(mode="json")
    body_digest = digest(json.dumps(normalized, sort_keys=True, ensure_ascii=False))

    def produce() -> dict:
        context = make_context(request, subject_id, x_request_id, body.curriculumSnapshotId)
        result = cast(
            SchoolProgressImportResult,
            tool_client.call(
                "importSchoolProgress",
                body,
                context,
                idempotency_key=idempotency_key,
            ),
        )
        return envelope(x_request_id, "OK", result).model_dump(mode="json")

    return idempotency.run(subject_id, "school-progress", idempotency_key, body_digest, produce)


@router.get("/api/v1/school-progress")
def get_school_progress(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
) -> dict:
    context = make_context(request, subject_id, x_request_id)
    result = cast(
        SchoolProgressImportResult,
        tool_client.call("getSchoolProgress", None, context),
    )
    return envelope(x_request_id, "OK", result).model_dump(mode="json")
