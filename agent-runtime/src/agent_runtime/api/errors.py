"""Contract-consistent error handling: every response is a shared Envelope."""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent_runtime.adapters.model_client import ModelInvalidOutput, ModelTimeout
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

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


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
            code=exc.issue_code, message=exc.message, field=exc.field, retryable=exc.retryable
        )
        return _json(request, exc.status_code, exc.status, [issue])

    @app.exception_handler(ModelTimeout)
    async def model_timeout(request: Request, exc: ModelTimeout) -> JSONResponse:
        issue = Issue(code="MODEL_TIMEOUT", message=str(exc), field=None, retryable=True)
        return _json(request, 504, "ERROR", [issue])

    @app.exception_handler(ModelInvalidOutput)
    async def model_invalid_output(request: Request, exc: ModelInvalidOutput) -> JSONResponse:
        issue = Issue(code="MODEL_INVALID_OUTPUT", message=str(exc), field=None, retryable=False)
        return _json(request, 422, "ERROR", [issue])

    @app.exception_handler(ToolContractViolation)
    async def tool_contract_violation(
        request: Request, exc: ToolContractViolation
    ) -> JSONResponse:
        # The provider answered; it just answered something the contract forbids.
        # Calling this 503 sends people looking for a dead service.
        issue = Issue(code="TOOL_CONTRACT_VIOLATION", message=str(exc), field=None, retryable=False)
        return _json(request, 502, "ERROR", [issue])

    @app.exception_handler(ToolRejected)
    async def tool_rejected(request: Request, exc: ToolRejected) -> JSONResponse:
        # Pass the provider's own status and reason through. Java's 404 means
        # "not visible or does not exist" (java.openapi.json) and must stay 404.
        status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
        issue = Issue(code=exc.issue_code, message=str(exc), field=None, retryable=False)
        return _json(request, status_code, "ERROR", [issue])

    @app.exception_handler(ToolUnavailable)
    async def tool_unavailable(request: Request, exc: ToolUnavailable) -> JSONResponse:
        issue = Issue(
            code="TOOL_UNAVAILABLE", message=f"Java 工具不可用: {exc}", field=None, retryable=False
        )
        return _json(request, 503, "ERROR", [issue])

    @app.exception_handler(InvalidTool)
    async def invalid_tool(request: Request, exc: InvalidTool) -> JSONResponse:
        issue = Issue(
            code="INVALID_TOOL", message=f"未登记的工具: {exc}", field="toolName", retryable=False
        )
        return _json(request, 422, "INVALID_INPUT", [issue])

    @app.exception_handler(BudgetExceeded)
    async def budget_exceeded(request: Request, exc: BudgetExceeded) -> JSONResponse:
        issue = Issue(code="BUDGET_EXCEEDED", message=str(exc), field=None, retryable=False)
        return _json(request, 503, "ERROR", [issue])

    @app.exception_handler(IdempotencyConflict)
    async def idempotency_conflict(request: Request, exc: IdempotencyConflict) -> JSONResponse:
        issue = Issue(
            code="IDEMPOTENCY_CONFLICT", message=str(exc), field="Idempotency-Key", retryable=False
        )
        return _json(request, 409, "CONFLICT", [issue])

    @app.exception_handler(RequestInProgress)
    async def request_in_progress(request: Request, exc: RequestInProgress) -> JSONResponse:
        issue = Issue(
            code="REQUEST_IN_PROGRESS", message=str(exc), field="Idempotency-Key", retryable=True
        )
        return _json(request, 409, "CONFLICT", [issue])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            Issue(
                code="INVALID_INPUT",
                message=str(err.get("msg")),
                field=".".join(str(part) for part in err.get("loc", [])),
                retryable=False,
            )
            for err in exc.errors()
        ]
        return _json(request, 422, "INVALID_INPUT", issues)
