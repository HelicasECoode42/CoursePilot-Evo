"""Compose bounded school facts with one typed model response."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from agent_runtime.adapters.model_client import (
    AdviceChatModelReply,
    FakeModelAdapter,
    ModelInvalidOutput,
)
from agent_runtime.adapters.tool_client import ToolClient, ToolPage, ToolRejected
from agent_runtime.api.errors import InvalidInputError
from agent_runtime.api.schemas import (
    AcademicRecord,
    Course,
    Issue,
    ReviewNote,
    SchoolProgressImportResult,
    SnapshotSummary,
)
from agent_runtime.api.schemas.advice_chat import (
    AdviceChatAnswer,
    AdviceChatCourse,
    AdviceChatRequest,
    AdviceChatSuggestion,
    AdviceSchoolProgress,
    AdviceSchoolProgressNode,
)
from agent_runtime.application.budget import Budget, BudgetExceeded, BudgetTracker
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import new_id

logger = logging.getLogger(__name__)


def _invalid_model_reply(
    message: str,
    reply: AdviceChatModelReply,
    context: ExecutionContext,
    *,
    field_path: str,
    reason_code: str,
) -> ModelInvalidOutput:
    diagnostics: dict[str, str | int | bool | None] = {
        "request_id": context.request_id,
        "stage": "advice_chat_fact_validation",
        "field_path": field_path,
        "reason_code": reason_code,
        "shape": reply.response_shape or "json_object",
        "finish_reason": reply.finish_reason,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
    }
    logger.warning(
        "Advice chat model output rejected: %s",
        json.dumps(diagnostics, sort_keys=True),
        extra={"advice_chat_diagnostics": diagnostics},
    )
    return ModelInvalidOutput(
        message,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        diagnostics=diagnostics,
    )


def _bigram_relevance(query: str, text: str) -> float:
    normalized_query = "".join(query.casefold().split())
    normalized_text = "".join(text.casefold().split())
    if not normalized_query or not normalized_text:
        return 0.0
    query_bigrams = {normalized_query[i : i + 2] for i in range(len(normalized_query) - 1)}
    text_bigrams = {normalized_text[i : i + 2] for i in range(len(normalized_text) - 1)}
    if not query_bigrams:
        return 1.0 if normalized_query in normalized_text else 0.0
    return len(query_bigrams & text_bigrams) / len(query_bigrams)


def _review_status(
    course_code: str,
    queried: set[str],
    unknown_for: set[str],
    reviews_by_course: dict[str, list[ReviewNote]],
) -> str:
    if course_code in unknown_for:
        return "UNKNOWN"
    if course_code in queried:
        return "AVAILABLE" if reviews_by_course.get(course_code) else "NONE"
    return "NOT_QUERIED"


class AdviceChatService:
    def __init__(
        self, *, tool_client: ToolClient, model_adapter, budget: Budget | None = None
    ) -> None:
        self._tools = tool_client
        self._model = model_adapter
        self._budget = budget or Budget(max_tool_calls=6, max_model_calls=1)

    def run(self, request: AdviceChatRequest, context: ExecutionContext) -> AdviceChatAnswer:
        tracker = BudgetTracker(self._budget)
        started = datetime.now(UTC)
        progress = None
        record = None
        courses: list[Course] = []
        reviews_by_course: dict[str, list[ReviewNote]] = {}
        queried: set[str] = set()
        reviews_unknown_for: set[str] = set()
        progress_mismatch = False
        catalogue_truncated = False

        def call(tool: str, params: dict | None = None):
            tracker.check_deadline()
            tracker.record_tool_call(tool)
            return self._tools.call(tool, None, context, params=params)

        def call_page(tool: str, params: dict):
            tracker.check_deadline()
            tracker.record_tool_call(tool)
            if hasattr(self._tools, "call_page"):
                return self._tools.call_page(tool, None, context, params=params)
            return self._tools.call(tool, None, context, params=params)

        try:
            progress_result = call("getSchoolProgress")
            if isinstance(progress_result, SchoolProgressImportResult):
                progress = progress_result
        except ToolRejected as exc:
            if not (
                (exc.status_code == 404 and exc.issue_code in {"NOT_VISIBLE", "NOT_FOUND"})
                or exc.issue_code == "SCHOOL_PROGRESS_UNAVAILABLE"
            ):
                raise

        snapshots = call("listCurricula")
        matching = next(
            (
                item
                for item in snapshots
                if isinstance(item, SnapshotSummary)
                and item.snapshotId == request.curriculumSnapshotId
            ),
            None,
        )
        if matching is None or matching.kind != "CURRICULUM" or matching.state != "PUBLISHED":
            raise InvalidInputError("培养方案不存在或当前不可用", field="curriculumSnapshotId")
        if request.mode == "REAL":
            usable = (
                matching.sourceKind != "SYNTHETIC"
                and matching.sourceValidation != "SYNTHETIC"
                and (
                    matching.sourceValidation == "VERIFIED"
                    or (
                        matching.sourceKind == "CURRICULUM_FILE"
                        and matching.sourceValidation == "UNVERIFIED"
                    )
                )
            )
        else:
            usable = (
                matching.sourceKind == "SYNTHETIC"
                or matching.sourceValidation == "SYNTHETIC"
                or (
                    matching.sourceKind == "CURRICULUM_FILE"
                    and matching.sourceValidation == "UNVERIFIED"
                )
            )
        if not usable:
            raise InvalidInputError("培养方案来源与当前模式不匹配", field="curriculumSnapshotId")

        if progress and (
            progress.academicRecord.curriculumSnapshotId != request.curriculumSnapshotId
            or (
                request.academicRecordId is not None
                and progress.academicRecord.academicRecordId != request.academicRecordId
            )
        ):
            progress = None
            progress_mismatch = True

        if request.academicRecordId:
            if progress and progress.academicRecord.academicRecordId == request.academicRecordId:
                record = progress.academicRecord
            else:
                record = call("getAcademicRecord", {"recordId": request.academicRecordId})
            if not isinstance(record, AcademicRecord):
                raise InvalidInputError("学业记录返回类型错误")
            if (
                record.academicRecordId != request.academicRecordId
                or record.curriculumSnapshotId != request.curriculumSnapshotId
            ):
                raise InvalidInputError("学业记录不属于当前培养方案", field="academicRecordId")
        elif (
            progress
            and progress.academicRecord.curriculumSnapshotId == request.curriculumSnapshotId
        ):
            record = progress.academicRecord

        course_page = call_page(
            "listCourses", {"curriculumSnapshotId": request.curriculumSnapshotId, "limit": 200}
        )
        if isinstance(course_page, ToolPage):
            catalogue_truncated = course_page.next_cursor is not None
            all_courses = course_page.items
        else:
            all_courses = course_page
        if not isinstance(all_courses, list):
            raise RuntimeError("课程目录返回类型错误")
        courses = [item for item in all_courses if isinstance(item, Course)]

        from agent_runtime.domain.policies.course_scope import eligible_course_codes

        record_courses = list(record.completedCourses) if record else []
        allowed = eligible_course_codes(
            courses, record_courses, explicitly_selected=request.selectedCourseCodes
        )
        if not record:
            # No Java academic record matches this curriculum in the current session.
            unknowns = [
                Issue(
                    code="ACADEMIC_RECORD_MISSING",
                    message="本会话没有适用于该培养方案的学业记录，无法据此排除已修课程。",
                    field="academicRecordId",
                    retryable=False,
                )
            ]
        else:
            unknowns = [
                Issue(
                    code="ACADEMIC_RECORD_UNKNOWN",
                    message=f"学业记录课程 {item.courseCode} 状态为 UNKNOWN，不能按已修处理。",
                    field="academicRecordId",
                    retryable=False,
                )
                for item in record_courses
                if item.outcome == "UNKNOWN"
            ]
        if isinstance(self._model, FakeModelAdapter):
            unknowns.append(
                Issue(
                    code="FAKE_MODEL",
                    message="当前回答由受控假模型生成。",
                    field=None,
                    retryable=False,
                )
            )
        if progress:
            unknowns.extend(
                Issue(
                    code="SCHOOL_PROGRESS_UNKNOWN",
                    message=(
                        f"学校进度课程 {item.courseCode} 状态为 UNKNOWN，不能按已修或未修处理。"
                    ),
                    field="schoolProgress",
                    retryable=False,
                )
                for item in progress.snapshot.courses
                if item.outcome == "UNKNOWN"
            )
        if progress_mismatch:
            unknowns.append(
                Issue(
                    code="SCHOOL_PROGRESS_RECORD_MISMATCH",
                    message="学校进度关联的培养方案或学业记录与本轮请求不一致，本轮未将其作为事实。",
                    field="schoolProgress",
                    retryable=False,
                )
            )
        if catalogue_truncated:
            unknowns.append(
                Issue(
                    code="COURSE_CATALOG_TRUNCATED",
                    message="课程目录仍有未读取页面，本轮候选范围不完整。",
                    field="courses",
                    retryable=False,
                )
            )

        selected_courses = [c for c in courses if c.courseCode in allowed]
        course_by_code = {c.courseCode: c for c in selected_courses}
        # The remaining per-turn tool budget is shared by bounded review lookups.
        review_limit = min(2, max(0, self._budget.max_tool_calls - tracker.tool_calls))
        context_terms = " ".join(
            [request.message, request.interestText]
            + [m.text for m in request.history if m.role == "user"]
        )
        prioritized_courses = sorted(
            selected_courses,
            key=lambda course: (
                course.courseCode not in request.selectedCourseCodes,
                course.courseCode not in request.preferredCourseCodes,
                -_bigram_relevance(context_terms, f"{course.name} {course.category}"),
                course.courseCode,
            ),
        )
        for course in prioritized_courses[:review_limit]:
            queried.add(course.courseCode)
            page = call_page("searchReviews", {"courseCode": course.courseCode, "limit": 5})
            if isinstance(page, ToolPage):
                notes = page.items
                if page.next_cursor is not None:
                    reviews_unknown_for.add(course.courseCode)
            else:
                notes = page if isinstance(page, list) else []
            usable_notes = notes
            if request.mode == "REAL":
                usable_notes = [note for note in usable_notes if note.sourceKind != "SYNTHETIC"]
                if notes and not usable_notes:
                    reviews_unknown_for.add(course.courseCode)
            reviews_by_course[course.courseCode] = usable_notes

        available_courses = [
            {
                "courseCode": c.courseCode,
                "name": c.name,
                "credits": float(c.credits) if c.credits is not None else None,
                "category": c.category,
                "reviewNoteIds": [n.reviewNoteId for n in reviews_by_course.get(c.courseCode, [])],
                "reviewStatus": _review_status(
                    c.courseCode, queried, reviews_unknown_for, reviews_by_course
                ),
            }
            for c in selected_courses
        ]
        model_payload = {
            "message": request.message,
            "confirmedInterest": request.interestText,
            "selectedCourseCodes": request.selectedCourseCodes,
            "preferredCourseCodes": request.preferredCourseCodes,
            "curriculumSource": {
                "sourceKind": matching.sourceKind,
                "sourceValidation": matching.sourceValidation,
            },
            "schoolProgress": self._model_progress(progress),
            "availableCourses": available_courses,
            "reviews": {
                code: [{**n.model_dump(mode="json"), "excerpt": n.excerpt[:300]} for n in notes]
                for code, notes in reviews_by_course.items()
            },
            "queriedCourseCodes": sorted(queried),
            "recordStatuses": [
                {"courseCode": item.courseCode, "outcome": item.outcome} for item in record_courses
            ],
            "recordSource": (
                "REQUESTED_ACADEMIC_RECORD"
                if request.academicRecordId
                else "SESSION_SCHOOL_PROGRESS"
                if progress and record
                else "UNAVAILABLE"
            ),
        }
        history = [m.model_dump(mode="json") for m in request.history]
        while True:
            encoded = json.dumps({**model_payload, "history": history}, ensure_ascii=False)
            estimated_input_tokens = (len(encoded.encode("utf-8")) + 2) // 3 + 250
            if estimated_input_tokens <= self._budget.max_input_tokens:
                break
            if history:
                history.pop(0)
                continue
            raise BudgetExceeded("对话事实和本轮消息超过 input token 预算")
        model_messages = [{"role": "user", "content": encoded}]
        tracker.record_model_call()
        try:
            model_reply: AdviceChatModelReply = self._model.generate_chat(
                context=context, messages=model_messages
            )
        except ModelInvalidOutput as exc:
            try:
                tracker.record_tokens(exc.input_tokens, exc.output_tokens)
            except BudgetExceeded as budget_exc:
                budget_exc.input_tokens = exc.input_tokens
                budget_exc.output_tokens = exc.output_tokens
                raise
            raise
        try:
            tracker.record_tokens(model_reply.input_tokens, model_reply.output_tokens)
        except BudgetExceeded as exc:
            exc.input_tokens = model_reply.input_tokens
            exc.output_tokens = model_reply.output_tokens
            raise

        rationale_map: dict[str, dict] = {}
        allowed_reviews = {
            (code, n.reviewNoteId) for code, notes in reviews_by_course.items() for n in notes
        }
        for index, item in enumerate(model_reply.courses):
            code = item["courseCode"]
            if code not in course_by_code:
                raise _invalid_model_reply(
                    "课程引用不匹配",
                    model_reply,
                    context,
                    field_path=f"courses[{index}].courseCode",
                    reason_code="COURSE_REFERENCE_MISMATCH",
                )
            refs = item["reviewNoteIds"]
            if not 1 <= len(item["reason"]) <= 500:
                raise _invalid_model_reply(
                    "回答结构错误",
                    model_reply,
                    context,
                    field_path=f"courses[{index}].reason",
                    reason_code="STRING_LENGTH",
                )
            if len(refs) > 10 or any((code, ref) not in allowed_reviews for ref in refs):
                raise _invalid_model_reply(
                    "课程评价引用不匹配",
                    model_reply,
                    context,
                    field_path=f"courses[{index}].reviewNoteIds",
                    reason_code="REVIEW_REFERENCE_MISMATCH",
                )
            rationale_map[code] = item

        completed_courses = []
        for code, rationale in rationale_map.items():
            course = course_by_code[code]
            notes = reviews_by_course.get(code, [])
            completed_courses.append(
                AdviceChatCourse(
                    courseCode=code,
                    name=course.name,
                    credits=course.credits,
                    category=course.category,
                    reason=rationale["reason"],
                    reviewNoteIds=rationale["reviewNoteIds"],
                    reviews=notes,
                    reviewStatus=_review_status(
                        code, queried, reviews_unknown_for, reviews_by_course
                    ),
                )
            )

        suggestions = []
        shown_codes = {x.courseCode for x in completed_courses}
        for index, raw in enumerate(model_reply.suggestions):
            kind, value = raw["kind"], raw["value"]
            if kind != "INTEREST" and value not in shown_codes:
                raise _invalid_model_reply(
                    "课程建议引用不匹配",
                    model_reply,
                    context,
                    field_path=f"suggestions[{index}].value",
                    reason_code="SUGGESTION_REFERENCE_MISMATCH",
                )
            if not 1 <= len(raw["label"]) <= 200 or not 1 <= len(value) <= 1000:
                raise _invalid_model_reply(
                    "回答结构错误",
                    model_reply,
                    context,
                    field_path=f"suggestions[{index}]",
                    reason_code="FIELD_LENGTH",
                )
            suggestions.append(AdviceChatSuggestion(suggestionId=new_id("suggestion"), **raw))

        school = None
        if progress:
            school = AdviceSchoolProgress(
                capturedAt=progress.snapshot.capturedAt.isoformat(),
                source=progress.snapshot.source,
                nodes=[
                    AdviceSchoolProgressNode(
                        nodeId=n.nodeId,
                        parentId=n.parentId,
                        name=n.name,
                        requiredCredits=n.requiredCredits,
                        earnedCredits=n.earnedCredits,
                        remainingCredits=n.remainingCredits,
                    )
                    for n in progress.snapshot.nodes
                ],
            )
        return AdviceChatAnswer(
            schemaVersion="1.0",
            reply=model_reply.reply,
            question=model_reply.question,
            courses=completed_courses,
            suggestions=suggestions,
            schoolProgress=school,
            unknowns=unknowns,
            usage={
                "inputTokens": tracker.input_tokens,
                "outputTokens": tracker.output_tokens,
                "toolCalls": tracker.tool_calls,
                "elapsedMs": int((datetime.now(UTC) - started).total_seconds() * 1000),
            },
        )

    @staticmethod
    def _model_progress(progress: SchoolProgressImportResult | None) -> dict | None:
        if not progress:
            return None
        # Grades and school credentials are deliberately omitted.
        return {
            "capturedAt": progress.snapshot.capturedAt.isoformat(),
            "source": progress.snapshot.source,
            "nodes": [n.model_dump(mode="json") for n in progress.snapshot.nodes],
            "courses": [
                {
                    "courseCode": c.courseCode,
                    "name": c.name,
                    "credits": c.credits,
                    "outcome": c.outcome,
                }
                for c in progress.snapshot.courses
            ],
        }
