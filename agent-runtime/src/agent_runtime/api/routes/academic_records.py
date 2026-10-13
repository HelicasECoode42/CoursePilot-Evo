"""POST/GET /api/v1/academic-records — save/read the session's completed courses."""

from __future__ import annotations

import json
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Request

from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.deps import get_idempotency, get_tool_client, make_context, require_subject
from agent_runtime.api.errors import envelope
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.schemas import AcademicRecord, AcademicRecordInput
from agent_runtime.application.ids import digest

router = APIRouter()


@router.post("/api/v1/academic-records", status_code=201)
def save_record(
    request: Request,
    body: AcademicRecordInput,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency)],
) -> dict:
    body_digest = digest(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    )
    cached = idempotency.resolve(subject_id, "academic-records", idempotency_key, body_digest)
    if cached is not None:
        return cached

    context = make_context(request, subject_id, x_request_id, body.curriculumSnapshotId)
    result = cast(AcademicRecord, tool_client.call("createAcademicRecord", body, context))
    payload = envelope(x_request_id, "OK", result).model_dump(mode="json")
    idempotency.store(subject_id, "academic-records", idempotency_key, body_digest, payload)
    return payload


@router.get("/api/v1/academic-records/{record_id}")
def read_record(
    request: Request,
    record_id: str,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
) -> dict:
    # Object-level scope is enforced by Java via the trusted X-Subject-Id header.
    context = make_context(request, subject_id, x_request_id)
    result = cast(
        AcademicRecord,
        tool_client.call("getAcademicRecord", None, context, params={"recordId": record_id}),
    )
    return envelope(x_request_id, "OK", result).model_dump(mode="json")


@router.get("/api/v1/academic-records")
def list_records(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
) -> dict:
    # List this session's saved records (empty items is a normal business state).
    context = make_context(request, subject_id, x_request_id)
    result = tool_client.call("listAcademicRecords", None, context)
    return envelope(x_request_id, "OK", {"items": result}).model_dump(mode="json")
