"""POST /api/v1/sessions — create an anonymous demo session."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from agent_runtime.api.deps import get_session_rate_limiter, get_session_store
from agent_runtime.api.errors import RateLimitedError, envelope
from agent_runtime.api.rate_limit import FixedWindowRateLimiter
from agent_runtime.api.schemas import SessionResult
from agent_runtime.api.session_store import SessionStore, SessionStoreFull
from agent_runtime.application.ids import new_id

router = APIRouter()


@router.post("/api/v1/sessions", status_code=201)
def create_session(
    request: Request,
    store: Annotated[SessionStore, Depends(get_session_store)],
    limiter: Annotated[FixedWindowRateLimiter, Depends(get_session_rate_limiter)],
) -> dict:
    # 分桶键是调用方地址。反向代理后面它是代理地址，限流会退化成全局配额——
    # 这是已知局限：建会话这一步还没有任何可信身份可用来按人分桶。
    caller = request.client.host if request.client else "unknown"
    if not limiter.check_and_record(caller):
        raise RateLimitedError("建会话过于频繁，请稍后再试")
    try:
        session_id, token, expires_at = store.create()
    except SessionStoreFull as exc:
        # 不是客户端的错，但也只能让它稍后再试；不静默返回一个假会话。
        raise RateLimitedError("服务当前的会话数已满，请稍后再试") from exc
    data = SessionResult(sessionId=session_id, sessionToken=token, expiresAt=expires_at)
    return envelope(new_id("req"), "OK", data).model_dump(mode="json")
