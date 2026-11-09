"""Section counts per course for the credits page, batched over one offering snapshot.

Used by POST /api/v1/offering-summary. The same rule as the planner applies: a short
unfiltered listOfferings page is the whole snapshot, so one call settles every course;
a full page forces one listOfferings call per course. A course whose call fails is
reported as unknown, never as "not offered". Calls are counted on a BudgetTracker
built from the default Budget, so one request stays inside Budget.max_offering_calls.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from agent_runtime.adapters.tool_client import (
    InvalidTool,
    ToolClient,
    ToolRejected,
    ToolUnavailable,
)
from agent_runtime.api.schemas import CourseOffering
from agent_runtime.application.budget import Budget, BudgetExceeded, BudgetTracker
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.offering_check import COURSE_OFFERING_LIMIT, OFFERING_PAGE_LIMIT


@dataclass(frozen=True)
class CourseSectionSummary:
    courseCode: str
    sectionCount: int
    teacherTexts: tuple[str, ...]


@dataclass(frozen=True)
class OfferingSummary:
    items: list[CourseSectionSummary] = field(default_factory=list)
    unknown_course_codes: list[str] = field(default_factory=list)


def _summary(code: str, rows: Iterable[CourseOffering]) -> CourseSectionSummary:
    rows = list(rows)
    texts = tuple(dict.fromkeys(row.teacherText for row in rows))[:5]
    return CourseSectionSummary(courseCode=code, sectionCount=len(rows), teacherTexts=texts)


def summarize_offerings(
    tool_client: ToolClient,
    context: ExecutionContext,
    *,
    curriculum_snapshot_id: str,
    offering_snapshot_id: str,
    course_codes: list[str],
) -> OfferingSummary:
    codes = list(dict.fromkeys(course_codes))
    budget = BudgetTracker(Budget())

    def list_offerings(course_code: str | None) -> list[CourseOffering]:
        budget.record_offering_call()
        params: dict[str, object] = {
            "curriculumSnapshotId": curriculum_snapshot_id,
            "offeringSnapshotId": offering_snapshot_id,
            "limit": OFFERING_PAGE_LIMIT if course_code is None else COURSE_OFFERING_LIMIT,
        }
        if course_code is not None:
            params["courseCode"] = course_code
        rows = tool_client.call("listOfferings", None, context, params=params)
        return list(rows)

    page: list[CourseOffering] | None
    try:
        page = list_offerings(None)
    except (BudgetExceeded, ToolUnavailable, ToolRejected, InvalidTool):
        page = None
    complete = page is not None and len(page) < OFFERING_PAGE_LIMIT
    grouped: dict[str, list[CourseOffering]] = {}
    if complete and page is not None:
        for row in page:
            grouped.setdefault(row.courseCode, []).append(row)

    summary = OfferingSummary()
    for code in codes:
        if complete:
            summary.items.append(_summary(code, grouped.get(code, [])))
            continue
        try:
            fetched = list_offerings(code)
        except (BudgetExceeded, ToolUnavailable, ToolRejected, InvalidTool):
            summary.unknown_course_codes.append(code)
            continue
        # A full course page may be cut short (Java has no cursor): report it as unknown.
        if len(fetched) >= COURSE_OFFERING_LIMIT:
            summary.unknown_course_codes.append(code)
            continue
        rows = [row for row in fetched if row.courseCode == code]
        summary.items.append(_summary(code, rows))
    return summary
