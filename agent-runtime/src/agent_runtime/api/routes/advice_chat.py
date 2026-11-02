"""POST /api/v1/advice/chat — one bounded advice turn."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from agent_runtime.api.deps import get_idempotency, get_spend_ledger, require_subject
from agent_runtime.api.errors import envelope
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.schemas.advice_chat import AdviceChatRequest
from agent_runtime.application.advice_chat import AdviceChatService
from agent_runtime.application.budget import SessionSpendLedger
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import digest

router = APIRouter()


def get_advice_chat(request: Request) -> AdviceChatService:
    return request.app.state.advice_chat


@router.post("/api/v1/advice/chat")
def advice_chat(
    request: Request,
    body: AdviceChatRequest,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    service: Annotated[AdviceChatService, Depends(get_advice_chat)],
    idempotency: Annotated[IdempotencyStore, Depends(get_idempotency)],
    spend_ledger: Annotated[SessionSpendLedger, Depends(get_spend_ledger)],
) -> dict:
    body_digest = digest(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    )

    def produce() -> dict:
        settings = request.app.state.settings
        context = ExecutionContext(
            subject_id=subject_id,
            request_id=x_request_id,
            curriculum_snapshot_id=body.curriculumSnapshotId,
            offering_snapshot_id=None,
            model_id=settings.model_id,
            temperature=settings.temperature,
            deadline=datetime.now(UTC) + timedelta(milliseconds=settings.deadline_ms),
            harness_version=request.app.state.harness.version,
        )
        # 与规划路由相同：先原子预留单次对话的最大用量，结束后按实际结算。
        reservation = spend_ledger.reserve(
            subject_id, settings.max_input_tokens, settings.max_output_tokens
        )
        try:
            answer = service.run(body, context)
        except Exception as exc:
            # ModelInvalidOutput 等异常上带着模型已返回的实际用量，按它结算；否则整笔释放。
            reservation.settle(
                getattr(exc, "input_tokens", None), getattr(exc, "output_tokens", None)
            )
            raise
        reservation.settle(answer.usage.inputTokens, answer.usage.outputTokens)
        return envelope(x_request_id, "OK", answer).model_dump(mode="json")

    return idempotency.run(
        subject_id,
        "advice-chat",
        idempotency_key,
        body_digest,
        produce,
        cache_failure=lambda exc: (
            getattr(exc, "input_tokens", None) is not None
            or getattr(exc, "output_tokens", None) is not None
        ),
    )
