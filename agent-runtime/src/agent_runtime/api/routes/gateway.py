"""Read-only gateway to the Java tool API (module B).

Thin pass-throughs: Python never recalculates credits or time rules, it only
forwards typed requests to Java (docs/04 section 1). With no Java endpoint
configured, ``ToolClient.call`` raises ToolUnavailable -> 503.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Query, Request

from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.deps import get_tool_client, make_context, require_subject
from agent_runtime.api.errors import envelope
from agent_runtime.api.schemas import AuditRequest, AuditResult

router = APIRouter()


@router.post("/api/v1/requirements/audit")
def audit_requirements(
    request: Request,
    body: AuditRequest,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
) -> dict:
    context = make_context(request, subject_id, x_request_id, body.curriculumSnapshotId)
    result = cast(AuditResult, tool_client.call("auditRequirements", body, context))
    return envelope(x_request_id, "OK", result).model_dump(mode="json")


@router.get("/api/v1/curriculum-snapshots")
def list_curricula(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
) -> dict:
    context = make_context(request, subject_id, x_request_id)
    result = tool_client.call("listCurricula", None, context)
    return envelope(x_request_id, "OK", {"items": result}).model_dump(mode="json")


@router.get("/api/v1/courses")
def list_courses(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
    curriculum_snapshot_id: Annotated[str, Query(alias="curriculumSnapshotId")],
    query: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> dict:
    context = make_context(request, subject_id, x_request_id, curriculum_snapshot_id)
    result = tool_client.call(
        "listCourses", None, context, params={"query": query, "limit": limit, "cursor": cursor}
    )
    return envelope(x_request_id, "OK", {"items": result, "nextCursor": None}).model_dump(
        mode="json"
    )


@router.get("/api/v1/teacher-course-options")
def list_teacher_course_options(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
    curriculum_snapshot_id: Annotated[str, Query(alias="curriculumSnapshotId")],
    course_code: Annotated[str | None, Query(alias="courseCode")] = None,
    query: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> dict:
    context = make_context(request, subject_id, x_request_id, curriculum_snapshot_id)
    result = tool_client.call(
        "listTeacherCourseOptions",
        None,
        context,
        params={"courseCode": course_code, "query": query, "limit": limit, "cursor": cursor},
    )
    return envelope(x_request_id, "OK", {"items": result, "nextCursor": None}).model_dump(
        mode="json"
    )


@router.get("/api/v1/reviews/search")
def search_reviews(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
    course_code: Annotated[str, Query(alias="courseCode")],
    teacher_key: Annotated[str | None, Query(alias="teacherKey")] = None,
    term_id: Annotated[str | None, Query(alias="termId")] = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> dict:
    context = make_context(request, subject_id, x_request_id)
    result = tool_client.call(
        "searchReviews",
        None,
        context,
        params={
            "courseCode": course_code,
            "teacherKey": teacher_key,
            "termId": term_id,
            "limit": limit,
        },
    )
    return envelope(x_request_id, "OK", {"items": result}).model_dump(mode="json")


@router.get("/api/v1/career-directions")
def list_career_directions(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
    subject_tag: Annotated[str | None, Query(alias="subjectTag")] = None,
) -> dict:
    context = make_context(request, subject_id, x_request_id)
    result = tool_client.call(
        "listCareerDirections", None, context, params={"subjectTag": subject_tag}
    )
    return envelope(x_request_id, "OK", {"items": result}).model_dump(mode="json")
