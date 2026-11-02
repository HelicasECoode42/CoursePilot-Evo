"""Compose bounded school facts with one typed model response."""

from __future__ import annotations

import json
import logging
from collections import Counter
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

# 发给模型的候选课程上限。候选按相关度排序后截取；模型只能引用这里列出的课程。
MAX_CANDIDATE_COURSES = 25
# 发给模型的历史只保留最近几条，每条截断。更早的对话不再重复计费。
MAX_HISTORY_MESSAGES = 4
MAX_HISTORY_CHARS = 500
# 系统指令（约 500 个中文字符）加上消息外壳的固定开销，按 token 估计。
PROMPT_OVERHEAD_TOKENS = 700
MAX_UNKNOWN_COURSES = 40


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

        from agent_runtime.domain.policies.course_scope import (
            eligible_course_codes,
            school_gap_categories,
            school_taken_codes,
        )

        record_courses = list(record.completedCourses) if record else []
        # 学校报告只在本轮与培养方案/学业记录一致时使用；缺口与 Java 审计分开表述。
        report_gaps = (
            school_gap_categories(progress.snapshot.nodes, {c.category for c in courses})
            if progress
            else frozenset()
        )
        report_taken = school_taken_codes(progress.snapshot.courses) if progress else frozenset()
        allowed = eligible_course_codes(
            courses,
            record_courses,
            explicitly_selected=request.selectedCourseCodes,
            gap_categories=report_gaps,
            school_taken_codes=report_taken,
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
                course.category not in report_gaps,
                -_bigram_relevance(context_terms, f"{course.name} {course.category}"),
                course.courseCode,
            ),
        )
        # 只把相关度最高的一部分候选交给模型；引用校验也只认这一部分。
        prioritized_courses = prioritized_courses[:MAX_CANDIDATE_COURSES]
        selected_courses = prioritized_courses
        course_by_code = {c.courseCode: c for c in selected_courses}
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
            # 学校报告的剩余学分（来源：学校报告），与 Java 审计结果分开给出。
            "schoolReportGaps": [
                {"category": node.name, "remainingCredits": str(node.remainingCredits)}
                for node in (progress.snapshot.nodes if progress else [])
                if node.name in report_gaps
            ],
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
        history = [
            {"role": m.role, "text": m.text[:MAX_HISTORY_CHARS]}
            for m in request.history[-MAX_HISTORY_MESSAGES:]
        ]
        while True:
            encoded = json.dumps({**model_payload, "history": history}, ensure_ascii=False)
            estimated_input_tokens = (
                len(encoded.encode("utf-8")) + 2
            ) // 3 + PROMPT_OVERHEAD_TOKENS
            if estimated_input_tokens <= self._budget.max_input_tokens:
                break
            if history:
                history.pop(0)
                continue
            # 学校进度已压缩，正常情况不会走到这里。走到这里说明事实本身超过单次输入上限，
            # 本轮没有调用模型，也没有消耗会话额度；提示要说清楚，不能冒充额度用完。
            raise BudgetExceeded(
                "本轮的课程事实超过单次回答的输入上限，模型未调用，未消耗会话额度。"
                "请缩小已选课程范围后重试。"
            )
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

        # 模型输出的引用是不可信的：越出候选集的课程/评价只丢弃该条目，保留其余回答，
        # 并在 unknowns 中说明；绝不补造课程，也不因单条引用失败而整轮不出回答。
        rationale_map: dict[str, dict] = {}
        dropped_items = 0
        for item in model_reply.courses:
            code = item["courseCode"]
            if code not in course_by_code or code in rationale_map:
                dropped_items += 1
                continue
            own_notes = {n.reviewNoteId for n in reviews_by_course.get(code, [])}
            refs = [ref for ref in item["reviewNoteIds"] if ref in own_notes]
            dropped_items += len(item["reviewNoteIds"]) - len(refs)
            rationale_map[code] = {**item, "reviewNoteIds": refs}

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
        for raw in model_reply.suggestions:
            kind, value = raw["kind"], raw["value"]
            # 课程动作只能指向本轮允许的课程；其它建议丢弃，不编造。
            if kind != "INTEREST" and value not in course_by_code:
                dropped_items += 1
                continue
            suggestions.append(AdviceChatSuggestion(suggestionId=new_id("suggestion"), **raw))
        if dropped_items:
            logger.info("advice chat dropped %d out-of-scope model items", dropped_items)
            unknowns.append(
                Issue(
                    code="MODEL_CITATION_DROPPED",
                    message="部分建议引用了本轮候选范围之外的课程或评价，已忽略这些条目。",
                    field="courses",
                    retryable=False,
                )
            )

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
        """学校进度的模型视图：只给课程计数和未知项。

        学校进度树（上百行）和逐门课程不进模型上下文。有缺口的类别已由
        schoolReportGaps 给出（同一份事实，不重复发送）；已修课程已由候选范围排除。
        成绩、学号、节点 ID 都不发给模型。
        """
        if not progress:
            return None
        outcome_counts = Counter(c.outcome for c in progress.snapshot.courses)
        unknown_courses = [
            {"courseCode": c.courseCode, "name": c.name}
            for c in progress.snapshot.courses
            if c.outcome == "UNKNOWN"
        ]
        return {
            "capturedAt": progress.snapshot.capturedAt.isoformat(),
            "source": progress.snapshot.source,
            "outcomeCounts": dict(outcome_counts),
            "unknownCourses": unknown_courses[:MAX_UNKNOWN_COURSES],
        }
