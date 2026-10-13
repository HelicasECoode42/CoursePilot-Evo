"""Typed HTTP client for the Java tool API (module B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


# Registered Java typed tools (contracts/java.openapi.json). The Runner and the
# ModelAdapter may only call these; any other name is rejected before HTTP.
TOOLS: dict[str, ToolSpec] = {
    "listCurricula": ToolSpec("GET", "/api/v1/curriculum-snapshots", SnapshotSummary),
    "listCourses": ToolSpec("GET", "/api/v1/courses", Course),
    "listOfferings": ToolSpec("GET", "/api/v1/offerings", CourseOffering),
    "listTeacherCourseOptions": ToolSpec(
        "GET", "/api/v1/teacher-course-options", TeacherCourseOption
    ),
    "searchReviews": ToolSpec("GET", "/api/v1/reviews/search", ReviewNote),
    "listCareerDirections": ToolSpec("GET", "/api/v1/career-directions", CareerDirection),
    "auditRequirements": ToolSpec("POST", "/api/v1/requirements/audit", AuditResult),
    "validatePlan": ToolSpec("POST", "/api/v1/plans/validate", PlanValidation),
    "createAcademicRecord": ToolSpec("POST", "/api/v1/academic-records", AcademicRecord),
    "getAcademicRecord": ToolSpec("GET", "/api/v1/academic-records/{recordId}", AcademicRecord),
}


class ToolClient:
    """``call(tool, dto, context, params=...)`` is the only entry point.

    It never accepts a model-supplied URL (c-agent.md section 2). Read-only Java
    queries may retry a transient network error once within budget; validation or
    input errors are never retried. With no Java endpoint configured every tool
    reports ``ToolUnavailable`` instead of pretending there is no conflict.
    """

    def __init__(self, base_url: str | None, service_key: str) -> None:
        self._base_url = base_url
        self._service_key = service_key

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
        # W2/W3: typed HTTP with X-Service-Key / X-Subject-Id / X-Request-Id and a
        # <=5s timeout. GET tools serialize ``params`` as the query string; POST
        # tools serialize ``dto`` as the body. The parsed Envelope ``data`` is
        # returned (a model for POST tools, a list for GET list tools).
        raise ToolUnavailable(tool)
