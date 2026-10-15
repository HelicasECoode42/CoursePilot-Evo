"""POST /api/v1/sessions — create an anonymous demo session."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from agent_runtime.api.deps import get_session_store
from agent_runtime.api.errors import envelope
from agent_runtime.api.schemas import SessionResult
from agent_runtime.api.session_store import SessionStore
from agent_runtime.application.ids import new_id

router = APIRouter()


@router.post("/api/v1/sessions", status_code=201)
def create_session(
    request: Request, store: Annotated[SessionStore, Depends(get_session_store)]
) -> dict:
    session_id, token, expires_at = store.create()
    data = SessionResult(sessionId=session_id, sessionToken=token, expiresAt=expires_at)
    return envelope(new_id("req"), "OK", data).model_dump(mode="json")
