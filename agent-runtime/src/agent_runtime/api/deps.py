"""FastAPI dependencies: app-state accessors, bearer-session and admin resolution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header, Request

from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.errors import ForbiddenError, UnauthorizedError
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.session_store import SessionNotFound, SessionStore
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.runner import PlanningRunner


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_idempotency(request: Request) -> IdempotencyStore:
    return request.app.state.idempotency


def get_tool_client(request: Request) -> ToolClient:
    return request.app.state.tool_client


def get_runner(request: Request) -> PlanningRunner:
    return request.app.state.runner


def require_subject(
    store: Annotated[SessionStore, Depends(get_session_store)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("缺少或非法的会话令牌")
    token = authorization[len("Bearer ") :].strip()
    try:
        return store.resolve(token)
    except SessionNotFound as exc:
        # docs/04 section 1: an expired/unknown session is 401 (the client re-starts),
        # not 404; 404 stays reserved for objects that do not belong to this session.
        raise UnauthorizedError("会话不存在或已过期") from exc


def require_admin(
    request: Request,
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    admin_key = request.app.state.settings.admin_key
    if not admin_key:
        raise ForbiddenError("未配置管理员密钥")
    if x_admin_key != admin_key:
        raise ForbiddenError("无报告权限")


def make_context(
    request: Request,
    subject_id: str,
    x_request_id: str,
    curriculum_snapshot_id: str = "",
    offering_snapshot_id: str | None = None,
) -> ExecutionContext:
    """Build a trusted context for a Java tool call.

    For the Runner the snapshots come from the PlanningRequest; for gateway
    pass-throughs they are empty (the Java side resolves them from the query).
    """
    settings = request.app.state.settings
    return ExecutionContext(
        subject_id=subject_id,
        request_id=x_request_id,
        curriculum_snapshot_id=curriculum_snapshot_id,
        offering_snapshot_id=offering_snapshot_id,
        model_id=settings.model_id,
        temperature=settings.temperature,
        deadline=datetime.now(UTC) + timedelta(milliseconds=45000),
        harness_version=request.app.state.harness.version,
    )
