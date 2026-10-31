"""Read-only gateway to the Java tool API (module B).

Thin pass-throughs: Python never recalculates credits or time rules, it only
forwards typed requests to Java (docs/04 section 1). With no Java endpoint
configured, ``ToolClient.call`` raises ToolUnavailable -> 503.
"""

from __future__ import annotations

import re
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Query, Request

from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.deps import get_tool_client, make_context, require_subject
from agent_runtime.api.errors import InvalidQueryError, envelope
from agent_runtime.api.schemas import AuditRequest, AuditResult

router = APIRouter()
_OFFSET_CURSOR = re.compile(r"^[0-9]{1,9}$")


def _validate_cursor(cursor: str | None) -> None:
    if cursor is not None and _OFFSET_CURSOR.fullmatch(cursor) is None:
        raise InvalidQueryError("cursor 格式不合法", field="cursor")


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


@router.get("/api/v1/offering-snapshots")
def list_offering_snapshots(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
) -> dict:
    # 只透传 Java 的 listOfferingSnapshots；不在这里筛选或猜测哪一份可用。
    context = make_context(request, subject_id, x_request_id)
    result = tool_client.call("listOfferingSnapshots", None, context)
    return envelope(x_request_id, "OK", {"items": result}).model_dump(mode="json")


@router.get("/api/v1/courses")
def list_courses(
    request: Request,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
    curriculum_snapshot_id: Annotated[str, Query(alias="curriculumSnapshotId")],
    query: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> dict:
    _validate_cursor(cursor)
    context = make_context(request, subject_id, x_request_id, curriculum_snapshot_id)
    page = tool_client.call_page(
        "listCourses",
        None,
        context,
        params={
            "curriculumSnapshotId": curriculum_snapshot_id,
            "query": query,
            "limit": limit,
            "cursor": cursor,
        },
    )
    return envelope(
        x_request_id, "OK", {"items": page.items, "nextCursor": page.next_cursor}
    ).model_dump(mode="json")


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
    _validate_cursor(cursor)
    context = make_context(request, subject_id, x_request_id, curriculum_snapshot_id)
    page = tool_client.call_page(
        "listTeacherCourseOptions",
        None,
        context,
        params={
            "curriculumSnapshotId": curriculum_snapshot_id,
            "courseCode": course_code,
            "query": query,
            "limit": limit,
            "cursor": cursor,
        },
    )
    return envelope(
        x_request_id, "OK", {"items": page.items, "nextCursor": page.next_cursor}
    ).model_dump(mode="json")


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
    cursor: Annotated[str | None, Query()] = None,
) -> dict:
    _validate_cursor(cursor)
    context = make_context(request, subject_id, x_request_id)
    result = tool_client.call_page(
        "searchReviews",
        None,
        context,
        params={
            "courseCode": course_code,
            "teacherKey": teacher_key,
            "termId": term_id,
            "limit": limit,
            "cursor": cursor,
        },
    )
    return envelope(
        x_request_id, "OK", {"items": result.items, "nextCursor": result.next_cursor}
    ).model_dump(mode="json")


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
