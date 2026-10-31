"""Typed HTTP client for the Java tool API (module B)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from agent_runtime.api.schemas import (
    AcademicRecord,
    AuditResult,
    CareerDirection,
    Course,
    CourseOffering,
    PlanValidation,
    ReviewNote,
    SchoolProgressImportResult,
    SnapshotSummary,
    TeacherCourseOption,
)
from agent_runtime.application.context import ExecutionContext


class ToolUnavailable(RuntimeError):
    """Java tool dependency is down or unconfigured (-> 503 ERROR, c-agent.md section 6)."""


class InvalidTool(RuntimeError):
    """toolName is not in the registered whitelist (-> 422)."""


class ToolContractViolation(RuntimeError):
    """Java answered, but the payload breaks the shared contract (-> 502).

    Deliberately not folded into ToolUnavailable. Pydantic's ValidationError
    subclasses ValueError, so catching ValueError around the parsing step turns
    "the provider broke the contract" into "the provider is down". That cost us
    a debugging session once already: the Java audit endpoint answered HTTP 200
    while putting non-ASCII text in requirementId and an empty sourceRefIds, and
    the only symptom here was TOOL_UNAVAILABLE. A contract break is not
    retryable and the message must name the offending field.
    """


class ToolRejected(RuntimeError):
    """Java answered with a 4xx and a reason (-> that same status).

    Never retried. A rejected service key or an object the subject may not see
    will not become valid on a second try, and reporting either as 503 hides
    a configuration or authorization problem behind "dependency down".
    """

    def __init__(self, tool: str, status_code: int, issue_code: str, message: str) -> None:
        super().__init__(f"{tool}: {status_code} {issue_code}: {message}")
        self.tool = tool
        self.status_code = status_code
        self.issue_code = issue_code


@dataclass(frozen=True)
class ToolSpec:
    method: str
    path: str
    response_model: type[BaseModel]
    listed: bool = False


@dataclass(frozen=True)
class ToolPage:
    """A Java list response including its pagination cursor."""

    items: list[BaseModel]
    next_cursor: str | None


# Registered Java typed tools (contracts/java.openapi.json). The Runner and the
# ModelAdapter may only call these; any other name is rejected before HTTP.
TOOLS: dict[str, ToolSpec] = {
    "listCurricula": ToolSpec("GET", "/api/v1/curriculum-snapshots", SnapshotSummary, listed=True),
    # 开课快照列表（contracts/java.openapi.json listOfferingSnapshots）。与 listCurricula 分开：
    # 开课快照不能混进培养方案列表，否则会被误当培养方案使用。
    "listOfferingSnapshots": ToolSpec(
        "GET", "/api/v1/offering-snapshots", SnapshotSummary, listed=True
    ),
    "listCourses": ToolSpec("GET", "/api/v1/courses", Course, listed=True),
    "listOfferings": ToolSpec("GET", "/api/v1/offerings", CourseOffering, listed=True),
    "listTeacherCourseOptions": ToolSpec(
        "GET", "/api/v1/teacher-course-options", TeacherCourseOption, listed=True
    ),
    "searchReviews": ToolSpec("GET", "/api/v1/reviews/search", ReviewNote, listed=True),
    "listCareerDirections": ToolSpec(
        "GET", "/api/v1/career-directions", CareerDirection, listed=True
    ),
    "auditRequirements": ToolSpec("POST", "/api/v1/requirements/audit", AuditResult),
    "validatePlan": ToolSpec("POST", "/api/v1/plans/validate", PlanValidation),
    "createAcademicRecord": ToolSpec("POST", "/api/v1/academic-records", AcademicRecord),
    "getAcademicRecord": ToolSpec("GET", "/api/v1/academic-records/{recordId}", AcademicRecord),
    # listSessionRecords (planning.openapi.json) is the gateway's list endpoint; the
    # Java side (java.openapi.json) still needs GET /api/v1/academic-records to back it.
    "listAcademicRecords": ToolSpec("GET", "/api/v1/academic-records", AcademicRecord, listed=True),
    "importSchoolProgress": ToolSpec("PUT", "/api/v1/school-progress", SchoolProgressImportResult),
    "getSchoolProgress": ToolSpec("GET", "/api/v1/school-progress", SchoolProgressImportResult),
}


class ToolClient:
    """``call(tool, dto, context, params=...)`` is the only entry point.

    It never accepts a model-supplied URL (c-agent.md section 2). Read-only Java
    queries may retry a transient network error once within budget; validation or
    input errors are never retried. With no Java endpoint configured every tool
    reports ``ToolUnavailable`` instead of pretending there is no conflict.
    """

    def __init__(
        self,
        base_url: str | None,
        service_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._service_key = service_key
        self._transport = transport

    def call(
        self,
        tool: str,
        dto: BaseModel | None,
        context: ExecutionContext,
        *,
        params: dict[str, object] | None = None,
        idempotency_key: str | None = None,
        _include_page: bool = False,
    ) -> Any:
        spec = TOOLS.get(tool)
        if spec is None:
            raise InvalidTool(tool)
        if self._base_url is None:
            raise ToolUnavailable(tool)

        path_params: dict[str, object] = {}
        query: dict[str, object] = {}
        for key, value in (params or {}).items():
            token = "{" + key + "}"
            if token in spec.path:
                path_params[key] = value
            elif value is not None:
                query[key] = value
        url = self._base_url + spec.path.format(**path_params)
        headers = {
            "X-Service-Key": self._service_key,
            "X-Subject-Id": context.subject_id,
            "X-Request-Id": context.request_id,
            "Accept": "application/json",
        }
        # 不转发这个头，Java 侧的幂等（唯一约束 + 乐观锁 + 并发冲突回放）在生产里
        # 永远不会触发：去重只剩本进程的内存表，重启即失效。Java 把这个头当可选，
        # 带上才会按 (主体, 键) 入账。
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        timeout = _timeout_seconds(context)
        body = dto.model_dump(mode="json") if dto is not None else None

        try:
            response = self._send(spec.method, url, headers, query, body, timeout)
        except httpx.HTTPError as exc:
            if spec.method != "GET":
                raise ToolUnavailable(tool) from exc
            # The retry must fit the budget left *now*, not the timeout computed before
            # the first attempt; with no usable budget left, report unavailable instead.
            retry_timeout = _remaining_timeout_seconds(context)
            if retry_timeout is None:
                raise ToolUnavailable(tool) from exc
            try:
                response = self._send(spec.method, url, headers, query, body, retry_timeout)
            except httpx.HTTPError as retry_exc:
                raise ToolUnavailable(tool) from retry_exc

        if response.status_code >= 500:
            # No usable answer: the dependency is down, which is retryable.
            raise ToolUnavailable(tool)
        if response.status_code >= 400:
            raise _rejection(tool, response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ToolContractViolation(f"{tool}: response body is not JSON") from exc
        if not isinstance(payload, dict):
            raise ToolContractViolation(f"{tool}: response is not a contract Envelope")

        if payload.get("status") == "ERROR":
            issue = (payload.get("issues") or [{}])[0]
            raise ToolRejected(
                tool, response.status_code, issue.get("code", "ERROR"), issue.get("message", "")
            )

        # OK and UNKNOWN both carry data: UNKNOWN means "this is as far as the
        # facts go", not "the query failed".
        data = payload.get("data")
        try:
            if spec.listed:
                # The contract says data is an object holding items. A bare array
                # is off contract even though it looks like a list.
                items = data.get("items") if isinstance(data, dict) else None
                if not isinstance(items, list):
                    raise ToolContractViolation(
                        f"{tool}: list endpoints answer with data.items (java.openapi.json)"
                    )
                parsed_items = [spec.response_model.model_validate(item) for item in items]
                if _include_page:
                    if "nextCursor" not in data:
                        raise ToolContractViolation(f"{tool}: list response is missing nextCursor")
                    next_cursor = data.get("nextCursor")
                    if next_cursor is not None and not isinstance(next_cursor, str):
                        raise ToolContractViolation(f"{tool}: nextCursor must be a string or null")
                    return ToolPage(parsed_items, next_cursor)
                return parsed_items
            if data is None:
                raise ToolContractViolation(
                    f"{tool}: data is null on a {payload.get('status')} response"
                )
            return spec.response_model.model_validate(data)
        except ValidationError as exc:
            raise ToolContractViolation(f"{tool}: off contract: {exc}") from exc
        except (TypeError, AttributeError) as exc:
            raise ToolContractViolation(f"{tool}: unexpected data shape: {data!r}"[:300]) from exc

    def call_page(
        self,
        tool: str,
        dto: BaseModel | None,
        context: ExecutionContext,
        *,
        params: dict[str, object] | None = None,
    ) -> ToolPage:
        """Call a listed tool while preserving the provider's nextCursor."""
        result = self.call(tool, dto, context, params=params, _include_page=True)
        if not isinstance(result, ToolPage):
            raise ToolContractViolation(f"{tool}: pagination requested for a non-list tool")
        return result

    def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        query: dict[str, object],
        body: dict | None,
        timeout: float,
    ) -> httpx.Response:
        if method not in {"GET", "POST", "PUT"}:
            raise InvalidTool(f"unsupported HTTP method for {method}")
        with httpx.Client(timeout=timeout, transport=self._transport) as client:
            return client.request(method, url, headers=headers, params=query, json=body)


_MIN_TIMEOUT_SECONDS = 0.1


def _timeout_seconds(context: ExecutionContext) -> float:
    remaining = (context.deadline - datetime.now(UTC)).total_seconds()
    return max(_MIN_TIMEOUT_SECONDS, min(5.0, remaining))


def _remaining_timeout_seconds(context: ExecutionContext) -> float | None:
    """Timeout for a retry, or None when the remaining budget cannot cover one attempt."""
    remaining = (context.deadline - datetime.now(UTC)).total_seconds()
    if remaining < _MIN_TIMEOUT_SECONDS:
        return None
    return min(5.0, remaining)


def _rejection(tool: str, response: httpx.Response) -> ToolRejected:
    """Carry the provider's own Issue code through instead of inventing one."""
    code, message = "UNKNOWN", response.text[:200]
    try:
        issues = response.json().get("issues") or []
        if issues:
            code = issues[0].get("code", code)
            message = issues[0].get("message", message)
    except ValueError:
        pass  # A 4xx body that is not JSON is still a rejection, just an opaque one.
    return ToolRejected(tool, response.status_code, code, message)
