"""Per-course section counts for the credits page (batched, one offering snapshot)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.deps import get_tool_client, make_context, require_subject
from agent_runtime.api.errors import envelope
from agent_runtime.api.schemas import Issue
from agent_runtime.api.schemas.offering_summary import (
    CourseSectionSummary,
    OfferingSummaryData,
    OfferingSummaryRequest,
)
from agent_runtime.application.offering_summary import summarize_offerings

router = APIRouter()


@router.post("/api/v1/offering-summary")
def offering_summary(
    request: Request,
    body: OfferingSummaryRequest,
    subject_id: Annotated[str, Depends(require_subject)],
    x_request_id: Annotated[str, Header(alias="X-Request-Id")],
    tool_client: Annotated[ToolClient, Depends(get_tool_client)],
) -> dict:
    context = make_context(request, subject_id, x_request_id, body.curriculumSnapshotId)
    result = summarize_offerings(
        tool_client,
        context,
        curriculum_snapshot_id=body.curriculumSnapshotId,
        offering_snapshot_id=body.offeringSnapshotId,
        course_codes=body.courseCodes,
    )
    data = OfferingSummaryData(
        curriculumSnapshotId=body.curriculumSnapshotId,
        offeringSnapshotId=body.offeringSnapshotId,
        items=[
            CourseSectionSummary(
                courseCode=item.courseCode,
                sectionCount=item.sectionCount,
                teacherTexts=list(item.teacherTexts),
            )
            for item in result.items
        ],
        unknownCourseCodes=result.unknown_course_codes,
    )
    if not result.unknown_course_codes:
        return envelope(x_request_id, "OK", data).model_dump(mode="json")
    issue = Issue(
        code="OFFERING_LOOKUP_FAILED",
        message="部分课程的班次查询失败，这些课程的开课情况未能确认",
        field="courseCodes",
        retryable=True,
    )
    return envelope(x_request_id, "UNKNOWN", data, issues=[issue]).model_dump(mode="json")
