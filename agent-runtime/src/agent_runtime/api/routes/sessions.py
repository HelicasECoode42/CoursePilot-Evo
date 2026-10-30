"""POST /api/v1/sessions — create an anonymous demo session."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from agent_runtime.api.deps import get_session_rate_limiter, get_session_store
from agent_runtime.api.errors import RateLimitedError, envelope
from agent_runtime.api.rate_limit import FixedWindowRateLimiter, client_rate_key
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
    # 分桶键：默认是直连对端地址。同机反向代理后面时需要 CP_TRUST_CF_CONNECTING_IP=true，
    # 才会改用 CF-Connecting-IP（且只信任回环对端）；否则所有访客共用一个全局配额。
    caller = client_rate_key(
        request.client.host if request.client else None,
        request.headers.get("CF-Connecting-IP"),
        trust_cf_connecting_ip=request.app.state.settings.trust_cf_connecting_ip,
    )
    if not limiter.check_and_record(caller):
        raise RateLimitedError("建会话过于频繁，请稍后再试")
    try:
        session_id, token, expires_at = store.create()
    except SessionStoreFull as exc:
        # 不是客户端的错，但也只能让它稍后再试；不静默返回一个假会话。
        raise RateLimitedError("服务当前的会话数已满，请稍后再试") from exc
    data = SessionResult(sessionId=session_id, sessionToken=token, expiresAt=expires_at)
    return envelope(new_id("req"), "OK", data).model_dump(mode="json")
