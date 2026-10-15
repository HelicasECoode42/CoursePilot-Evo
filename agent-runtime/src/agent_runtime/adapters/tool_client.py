"""Typed HTTP client for the Java tool API (module B)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel

from agent_runtime.api.schemas import (
    AcademicRecord,
    AuditResult,
    CareerDirection,
    Course,
    CourseOffering,
    PlanValidation,
    ReviewNote,
    SnapshotSummary,
    TeacherCourseOption,
)
from agent_runtime.application.context import ExecutionContext


class ToolUnavailable(RuntimeError):
    """Java tool dependency is down or unconfigured (-> 503 ERROR, c-agent.md section 6)."""


class InvalidTool(RuntimeError):
    """toolName is not in the registered whitelist (-> 422)."""


@dataclass(frozen=True)
class ToolSpec:
    method: str
    path: str
    response_model: type[BaseModel]
    listed: bool = False


# Registered Java typed tools (contracts/java.openapi.json). The Runner and the
# ModelAdapter may only call these; any other name is rejected before HTTP.
TOOLS: dict[str, ToolSpec] = {
    "listCurricula": ToolSpec("GET", "/api/v1/curriculum-snapshots", SnapshotSummary, listed=True),
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
        timeout = _timeout_seconds(context)
        body = dto.model_dump(mode="json") if dto is not None else None

        try:
            response = self._send(spec.method, url, headers, query, body, timeout)
        except httpx.HTTPError as exc:
            if spec.method != "GET":
                raise ToolUnavailable(tool) from exc
            try:
                response = self._send(spec.method, url, headers, query, body, timeout)
            except httpx.HTTPError as retry_exc:
                raise ToolUnavailable(tool) from retry_exc

        if response.status_code >= 400:
            raise ToolUnavailable(tool)
        try:
            payload = response.json()
            data = payload.get("data")
            if spec.listed:
                items = data.get("items") if isinstance(data, dict) else data
                return [spec.response_model.model_validate(item) for item in items or []]
            return spec.response_model.model_validate(data)
        except (ValueError, TypeError, KeyError) as exc:
            raise ToolUnavailable(tool) from exc

    def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        query: dict[str, object],
        body: dict | None,
        timeout: float,
    ) -> httpx.Response:
        with httpx.Client(timeout=timeout, transport=self._transport) as client:
            if method == "GET":
                return client.get(url, headers=headers, params=query)
            return client.post(url, headers=headers, params=query, json=body)


def _timeout_seconds(context: ExecutionContext) -> float:
    remaining = (context.deadline - datetime.now(UTC)).total_seconds()
    return max(0.1, min(5.0, remaining))
