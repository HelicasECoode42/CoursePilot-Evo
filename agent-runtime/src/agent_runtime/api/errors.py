"""Contract-consistent error handling: every response is a shared Envelope."""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent_runtime.adapters.model_client import (
    ModelInvalidOutput,
    ModelTimeout,
    ModelUpstreamError,
)
from agent_runtime.adapters.tool_client import (
    InvalidTool,
    ToolContractViolation,
    ToolRejected,
    ToolUnavailable,
)
from agent_runtime.api.idempotency import IdempotencyConflict, RequestInProgress
from agent_runtime.api.schemas import Envelope, Issue
from agent_runtime.application.budget import BudgetExceeded
from agent_runtime.application.ids import new_id
from agent_runtime.application.plan_replacement import ReusedVerification
from agent_runtime.application.plan_store import PlanNotInSession

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")

# Issue.message is capped at 500 and Issue.code at 80 (api/schemas/_base.py). A
# longer string makes Issue() raise inside the handler, and that escapes as a 500.
_MESSAGE_LIMIT = 500
_CODE_LIMIT = 80
_TRUNCATED_MARK = "……[已截断]"


def _bounded(text: str, limit: int = _MESSAGE_LIMIT) -> str:
    """Return text that fits Issue.message: non-empty and within limit.

    Keeps the prefix, because the start of a pydantic error (which tool, which
    field) is the useful part, and marks the cut so nobody reads a partial
    message as complete.
    """
    text = text or "(无详情)"
    if len(text) <= limit:
        return text
    return text[: limit - len(_TRUNCATED_MARK)] + _TRUNCATED_MARK


_FIELD_LIMIT = 200


def _bounded_field(text: str | None) -> str | None:
    """Same guard as _bounded, for Issue.field (capped at 200, or absent).

    A deeply nested validation `loc` joins into a long path, and an over-long
    field makes Issue() raise inside the handler just like an over-long message.
    """
    if not text:
        return None
    return _bounded(text, _FIELD_LIMIT)


def _transient(status_code: int) -> bool:
    """Retry hint by status: 429 (rate limit) and 503/504 (dependency down or deadline).

    502 is excluded on purpose: it is used for contract violations, which are
    deterministic and fail the same way on every retry.
    """
    return status_code in (429, 503, 504)


# Java 的业务拒绝：请求本身合规，是被指到的对象或状态不满足规则。这些不是契约不一致，
# 原样透给调用方才有用——学生选了不存在的培养方案，该看到「没这个培养方案」，
# 不是「网关坏了」。对照 java-environment/.../web/ApiExceptionHandler.java 的分支：
#   422 SNAPSHOT_NOT_FOUND                （:88-89）
#   409 CONFLICT                          （:81-82）
#   409 SNAPSHOT_COURSE_FACTS_UNKNOWN     （:102-103）
#   409 SNAPSHOT_MISMATCH                 （:109-110）
# 这两个状态码在 planning.openapi.json 的每个相关端点都已声明。
# Java 的 400（INVALID_INPUT / INVALID_QUERY / MISSING_PARAMETER / MALFORMED_JSON 等）
# 不在此列：那表示本服务把请求拼错了，确实是违约，仍然判 502。
_JAVA_BUSINESS_REJECTIONS: dict[tuple[int, str], tuple[int, str]] = {
    (422, "SNAPSHOT_NOT_FOUND"): (422, "INVALID_INPUT"),
    (409, "CONFLICT"): (409, "CONFLICT"),
    (409, "SNAPSHOT_COURSE_FACTS_UNKNOWN"): (409, "CONFLICT"),
    (409, "SNAPSHOT_MISMATCH"): (409, "CONFLICT"),
}


def _rejected_response(exc: ToolRejected) -> tuple[int, str, Issue]:
    """Decide what the browser sees when Java answered with an error envelope.

    Only outcomes about the subject's own access pass through: NOT_VISIBLE (404,
    the object is absent or not in this session; the wording is deliberately
    shared) and FORBIDDEN (403). Anything else is about our own setup or about
    Java not matching the contract, and must not look like a user-level answer.

    - 401 (SERVICE_KEY_INVALID): our X-Service-Key is wrong or missing. That is
      our configuration. Passing 401 through would say "unauthenticated" to the
      browser and hint at internal config, so it becomes 503 TOOL_UNAVAILABLE
      with a generic message. Not retryable until the config is fixed.
    - 404 (NOT_FOUND, not NOT_VISIBLE): the route is missing, so Java's version
      does not match java.openapi.json. That is a contract violation, 502.
    - 429: Java is rate limiting us. Transient, so 429 and retryable.
    - Any other Java 4xx, or a 200 carrying an ERROR envelope: contract
      violation, 502.
    """
    if exc.status_code == 404 and exc.issue_code == "NOT_VISIBLE":
        issue = Issue(code="NOT_VISIBLE", message=_bounded(str(exc)), field=None, retryable=False)
        return 404, "NOT_FOUND", issue
    if exc.status_code == 403 and exc.issue_code == "FORBIDDEN":
        issue = Issue(code="FORBIDDEN", message=_bounded(str(exc)), field=None, retryable=False)
        return 403, "FORBIDDEN", issue
    if exc.status_code == 401:
        issue = Issue(
            code="TOOL_UNAVAILABLE",
            message=_bounded(f"{exc.tool}: 工具鉴权失败，请检查服务密钥配置"),
            field=None,
            retryable=False,
        )
        return 503, "ERROR", issue
    if exc.status_code == 429:
        issue = Issue(
            code="TOOL_RATE_LIMITED",
            message=_bounded(f"{exc.tool}: 工具限流，请稍后重试"),
            field=None,
            retryable=_transient(429),
        )
        return 429, "ERROR", issue
    mapped = _JAVA_BUSINESS_REJECTIONS.get((exc.status_code, exc.issue_code))
    if mapped is not None:
        status_code, envelope_status = mapped
        # 保留 Java 的原始 code：前端要据此区分「快照不存在」和「记录版本不一致」。
        issue = Issue(code=exc.issue_code, message=_bounded(str(exc)), field=None, retryable=False)
        return status_code, envelope_status, issue
    issue = Issue(
        code="TOOL_CONTRACT_VIOLATION",
        message=_bounded(
            f"{exc.tool}: Java 返回 {exc.status_code} {exc.issue_code}，与 java.openapi.json 不一致"
        ),
        field=None,
        retryable=False,
    )
    return 502, "ERROR", issue


def envelope(
    request_id: str,
    status: str,
    data: Any,
    *,
    trace_id: str | None = None,
    issues: list[Issue] | None = None,
    provenance: list[Any] | None = None,
) -> Envelope:
    return Envelope(
        schemaVersion="1.0",
        requestId=request_id,
        traceId=trace_id,
        status=status,
        data=data,
        provenance=provenance or [],
        issues=issues or [],
    )


class ApiError(Exception):
    status_code = 500
    status = "ERROR"
    issue_code = "ERROR"

    def __init__(self, message: str, *, field: str | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.retryable = retryable


class UnauthorizedError(ApiError):
    status_code = 401
    status = "UNAUTHORIZED"
    issue_code = "UNAUTHORIZED"


class NotFoundError(ApiError):
    status_code = 404
    status = "NOT_FOUND"
    issue_code = "NOT_FOUND"


class InvalidInputError(ApiError):
    status_code = 422
    status = "INVALID_INPUT"
    issue_code = "INVALID_INPUT"

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        code: str = "INVALID_INPUT",
    ) -> None:
        super().__init__(message, field=field)
        self.issue_code = code


class InvalidQueryError(ApiError):
    status_code = 400
    status = "INVALID_INPUT"
    issue_code = "INVALID_QUERY"


class ForbiddenError(ApiError):
    status_code = 403
    status = "FORBIDDEN"
    issue_code = "FORBIDDEN"


def _request_id(request: Request) -> str:
    raw = request.headers.get("X-Request-Id")
    if raw and _ID_RE.fullmatch(raw):
        return raw
    return new_id("req")


def _json(request: Request, status_code: int, status: str, issues: list[Issue]) -> JSONResponse:
    body = envelope(_request_id(request), status, {}, issues=issues)
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        issue = Issue(
            code=_bounded(exc.issue_code or "ERROR", _CODE_LIMIT),
            message=_bounded(exc.message),
            field=_bounded_field(exc.field),
            retryable=exc.retryable,
        )
        return _json(request, exc.status_code, exc.status, [issue])

    @app.exception_handler(ModelTimeout)
    async def model_timeout(request: Request, exc: ModelTimeout) -> JSONResponse:
        issue = Issue(
            code="MODEL_TIMEOUT", message=_bounded(str(exc)), field=None, retryable=_transient(504)
        )
        return _json(request, 504, "ERROR", [issue])

    @app.exception_handler(ModelUpstreamError)
    async def model_upstream(request: Request, exc: ModelUpstreamError) -> JSONResponse:
        if exc.status_code == 429:
            issue = Issue(
                code="MODEL_RATE_LIMITED",
                message=_bounded(str(exc)),
                field=None,
                retryable=_transient(429),
            )
            return _json(request, 429, "ERROR", [issue])
        issue = Issue(
            code="MODEL_UNAVAILABLE",
            message=_bounded(str(exc)),
            field=None,
            retryable=_transient(503),
        )
        return _json(request, 503, "ERROR", [issue])

    @app.exception_handler(ModelInvalidOutput)
    async def model_invalid_output(request: Request, exc: ModelInvalidOutput) -> JSONResponse:
        # Bad model output is a deterministic defect in this request, not a transient fault.
        issue = Issue(
            code="MODEL_INVALID_OUTPUT",
            message=_bounded(str(exc)),
            field=None,
            retryable=False,
        )
        return _json(request, 422, "ERROR", [issue])

    @app.exception_handler(ToolContractViolation)
    async def tool_contract_violation(request: Request, exc: ToolContractViolation) -> JSONResponse:
        # The provider answered; it just answered something the contract forbids.
        # Calling this 503 sends people looking for a dead service. It is 502 but
        # not retryable: a contract break is deterministic, so a retry gets the
        # same answer. _transient() deliberately does not cover 502 for this reason.
        issue = Issue(
            code="TOOL_CONTRACT_VIOLATION",
            message=_bounded(str(exc)),
            field=None,
            retryable=False,
        )
        return _json(request, 502, "ERROR", [issue])

    @app.exception_handler(ToolRejected)
    async def tool_rejected(request: Request, exc: ToolRejected) -> JSONResponse:
        status_code, status, issue = _rejected_response(exc)
        return _json(request, status_code, status, [issue])

    @app.exception_handler(ToolUnavailable)
    async def tool_unavailable(request: Request, exc: ToolUnavailable) -> JSONResponse:
        issue = Issue(
            code="TOOL_UNAVAILABLE",
            message=_bounded(f"Java 工具不可用: {exc}"),
            field=None,
            retryable=_transient(503),
        )
        return _json(request, 503, "ERROR", [issue])

    @app.exception_handler(InvalidTool)
    async def invalid_tool(request: Request, exc: InvalidTool) -> JSONResponse:
        issue = Issue(
            code="INVALID_TOOL",
            message=_bounded(f"未登记的工具: {exc}"),
            field="toolName",
            retryable=False,
        )
        return _json(request, 422, "INVALID_INPUT", [issue])

    @app.exception_handler(BudgetExceeded)
    async def budget_exceeded(request: Request, exc: BudgetExceeded) -> JSONResponse:
        issue = Issue(
            code="BUDGET_EXCEEDED", message=_bounded(str(exc)), field=None, retryable=False
        )
        return _json(request, 503, "ERROR", [issue])

    @app.exception_handler(IdempotencyConflict)
    async def idempotency_conflict(request: Request, exc: IdempotencyConflict) -> JSONResponse:
        issue = Issue(
            code="IDEMPOTENCY_CONFLICT",
            message=_bounded(str(exc)),
            field="Idempotency-Key",
            retryable=False,
        )
        return _json(request, 409, "CONFLICT", [issue])

    @app.exception_handler(PlanNotInSession)
    async def plan_not_in_session(request: Request, exc: PlanNotInSession) -> JSONResponse:
        del exc
        issue = Issue(
            code="NOT_FOUND",
            message="方案不在当前会话",
            field="previousPlanId",
            retryable=False,
        )
        return _json(request, 404, "NOT_FOUND", [issue])

    @app.exception_handler(ReusedVerification)
    async def reused_verification(request: Request, exc: ReusedVerification) -> JSONResponse:
        del exc
        issue = Issue(
            code="VERIFICATION_REUSED",
            message="核验结果复用了旧判决编号，已拒绝",
            field="verifierResultId",
            retryable=False,
        )
        return _json(request, 422, "INVALID_INPUT", [issue])

    @app.exception_handler(RequestInProgress)
    async def request_in_progress(request: Request, exc: RequestInProgress) -> JSONResponse:
        issue = Issue(
            code="REQUEST_IN_PROGRESS",
            message=_bounded(str(exc)),
            field="Idempotency-Key",
            retryable=True,
        )
        return _json(request, 409, "CONFLICT", [issue])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            Issue(
                code="INVALID_INPUT",
                message=_bounded(str(err.get("msg"))),
                field=_bounded_field(".".join(str(part) for part in err.get("loc", []))),
                retryable=False,
            )
            for err in exc.errors()
        ]
        return _json(request, 422, "INVALID_INPUT", issues)
