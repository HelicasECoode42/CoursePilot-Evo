"""The single Planning Runner shared by production and the benchmark."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import (
    FACTS_MESSAGE_PREFIX,
    FakeModelAdapter,
    ModelAdapter,
    ModelInvalidOutput,
    ModelReply,
    ModelTimeout,
)
from agent_runtime.adapters.result_repository import FileResultRepository
from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.adapters.trace_port import TracePort
from agent_runtime.api.schemas import (
    AuditRequest,
    AuditResult,
    Course,
    Issue,
    PlanningAnswer,
    PlanningRequest,
    PlanValidation,
    PlanValidationRequest,
    TeacherCourseOption,
    Usage,
)
from agent_runtime.application.budget import Budget, BudgetTracker
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import digest, new_id
from agent_runtime.application.run_manifest import RunIdentity, build_run_manifest
from agent_runtime.domain.policies.answer_compiler import AnswerCompiler
from agent_runtime.domain.policies.candidate_guard import CandidateGuard, KnownFacts
from agent_runtime.domain.policies.clarification_policy import ClarificationPolicy
from agent_runtime.domain.policies.intent_resolver import IntentResolver


class PlanningRunner:
    """The unique production/evaluation Runner (c-agent.md section 2).

    ``run(request, context) -> PlanningAnswer`` is the single entry point used by
    both the API and the benchmark harness (C-06); the same model config and tool
    set apply to both, so there is no evaluation-only Agent.
    """

    def __init__(
        self,
        *,
        tool_client: ToolClient,
        harness: HarnessSnapshot,
        model_adapter: ModelAdapter | None = None,
        intent_resolver: IntentResolver | None = None,
        clarification_policy: ClarificationPolicy | None = None,
        answer_compiler: AnswerCompiler | None = None,
        candidate_guard: CandidateGuard | None = None,
        result_repository: FileResultRepository | None = None,
        run_identity: RunIdentity | None = None,
        budget: Budget | None = None,
    ) -> None:
        self._tools = tool_client
        self._harness = harness
        self._model = model_adapter or FakeModelAdapter()
        self._budget = budget or Budget()
        self._intent_resolver = intent_resolver or IntentResolver()
        self._clarification = clarification_policy or ClarificationPolicy()
        self._answer = answer_compiler or AnswerCompiler()
        self._guard = candidate_guard or CandidateGuard()
        self._results = result_repository
        self._run_identity = run_identity or RunIdentity()

    def run(self, request: PlanningRequest, context: ExecutionContext) -> PlanningAnswer:
        task_id = new_id("task")
        trace_id = new_id("trace")
        trace = TracePort(
            task_id=task_id,
            trace_id=trace_id,
            harness_version=self._harness.version,
            curriculum_snapshot_id=request.curriculumSnapshotId,
            offering_snapshot_id=request.offeringSnapshotId,
        )
        budget = BudgetTracker(self._budget)
        started = datetime.now(UTC)

        trace.emit("USER_INPUT", input_digest=digest(request.promptText))

        resolved = self._intent_resolver.resolve(request)
        trace.emit("GOAL_EXTRACTED", input_digest=digest(request.promptText))

        audit = cast(
            AuditResult,
            self._call_tool(
                "auditRequirements",
                AuditRequest(
                    schemaVersion="1.0",
                    curriculumSnapshotId=request.curriculumSnapshotId,
                    academicRecordId=request.academicRecordId,
                ),
                context,
                budget,
                trace,
            ),
        )

        if resolved.needs_clarification:
            usage = self._usage(budget, started)
            question = self._clarification.build_question(resolved)
            trace.emit("CLARIFICATION_REQUESTED", output_ref=question.questionId)
            answer = self._answer.clarify(
                task_id=task_id, trace_id=trace_id, audit=audit, question=question, usage=usage
            )
            return self._deliver(answer, trace, context)

        facts = self._collect_facts(request, audit, context, budget, trace)
        reply = self._propose(request, context, facts, budget, trace)
        usage = self._usage(budget, started)

        if reply.clarify is not None:
            trace.emit("CLARIFICATION_REQUESTED", output_ref=reply.clarify.questionId)
            answer = self._answer.clarify(
                task_id=task_id,
                trace_id=trace_id,
                audit=audit,
                question=reply.clarify,
                usage=usage,
            )
            return self._deliver(self._mark_fake_model(answer), trace, context)

        items = reply.items or []
        guard_issues = self._guard.check(items, facts)
        if guard_issues or not items:
            answer = self._answer.unable_to_verify(
                task_id=task_id,
                trace_id=trace_id,
                audit=audit,
                issues=guard_issues
                or [
                    Issue(
                        code="EVIDENCE_MISMATCH",
                        message="没有可用的工具内课程候选",
                        field=None,
                        retryable=False,
                    )
                ],
                usage=usage,
            )
            trace.emit("ERROR", error_code="EVIDENCE_MISMATCH")
            return self._deliver(self._mark_fake_model(answer), trace, context)

        trace.emit("CANDIDATE_PROPOSED", output_ref=items[0].courseCode)
        verdict = cast(
            PlanValidation,
            self._call_tool(
                "validatePlan",
                PlanValidationRequest(
                    schemaVersion="1.0",
                    curriculumSnapshotId=request.curriculumSnapshotId,
                    offeringSnapshotId=request.offeringSnapshotId,
                    academicRecordId=request.academicRecordId,
                    mode=request.mode,
                    items=items,
                    hardConstraints=request.intent.hardConstraints,
                ),
                context,
                budget,
                trace,
            ),
        )
        trace.emit("VERIFIER_RETURNED", output_ref=verdict.verifierResultId)

        recommendation = self._answer.recommend(
            plan_id=new_id("plan"),
            items=items,
            explanation=(
                "课程层建议来自工具返回的课程集合，并已经过核验器判决；"
                "当前核验不是真实课表无冲突证明。"
            ),
            review_note_ids=[],
            verdict=verdict,
        )
        unknowns = self._with_fake_model_issue(list(verdict.unknownChecks) + list(audit.unknowns))
        answer = self._answer.recommendations(
            task_id=task_id,
            trace_id=trace_id,
            audit=audit,
            recommendations=[recommendation],
            usage=usage,
            unknowns=unknowns,
        )
        return self._deliver(answer, trace, context)

    def _collect_facts(
        self,
        request: PlanningRequest,
        audit: AuditResult,
        context: ExecutionContext,
        budget: BudgetTracker,
        trace: TracePort,
    ) -> KnownFacts:
        courses = cast(
            list[Course],
            self._call_tool(
                "listCourses",
                None,
                context,
                budget,
                trace,
                params={"curriculumSnapshotId": request.curriculumSnapshotId},
            ),
        )
        options = cast(
            list[TeacherCourseOption],
            self._call_tool(
                "listTeacherCourseOptions",
                None,
                context,
                budget,
                trace,
                params={"curriculumSnapshotId": request.curriculumSnapshotId},
            ),
        )
        course_codes = {course.courseCode for course in courses} | set(audit.suggestedCourseCodes)
        teacher_keys = {option.teacherKey for option in options}
        class_ids = {class_id for option in options for class_id in option.classIds}
        return KnownFacts(
            course_codes=frozenset(course_codes),
            teacher_keys=frozenset(teacher_keys),
            class_ids=frozenset(class_ids),
        )

    def _propose(
        self,
        request: PlanningRequest,
        context: ExecutionContext,
        facts: KnownFacts,
        budget: BudgetTracker,
        trace: TracePort,
    ) -> ModelReply | None:
        messages = [
            {
                "role": "system",
                "content": "只从 AVAILABLE_FACTS 里的 id 提候选，最多 3 条，禁止编造。",
            },
            {"role": "user", "content": request.promptText},
            {
                "role": "user",
                "content": FACTS_MESSAGE_PREFIX
                + json.dumps(
                    {
                        "courseCodes": sorted(facts.course_codes),
                        "teacherKeys": sorted(facts.teacher_keys),
                        "classIds": sorted(facts.class_ids),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        last_error: ModelInvalidOutput | None = None
        for _attempt in range(2):
            budget.record_model_call()
            budget.check_deadline()
            try:
                reply = self._model.generate(context=context, messages=messages, tool_schemas=[])
            except ModelTimeout:
                raise
            except ModelInvalidOutput as exc:
                last_error = exc
                continue
            budget.record_tokens(reply.input_tokens, reply.output_tokens)
            if reply.clarify is not None:
                return reply
            # An empty candidate list is missing data, not a broken model payload.
            return ModelReply(
                items=list(reply.items or []),
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
            )
        raise last_error or ModelInvalidOutput("模型输出无法解析为候选，已停止修复")

    def _call_tool(
        self,
        name: str,
        dto: Any,
        context: ExecutionContext,
        budget: BudgetTracker,
        trace: TracePort,
        *,
        params: dict[str, object] | None = None,
    ) -> Any:
        budget.record_tool_call()
        budget.check_deadline()
        trace.emit("TOOL_CALLED", tool_name=name)
        started = datetime.now(UTC)
        result = self._tools.call(name, dto, context, params=params)
        duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        output_ref = None
        if hasattr(result, "academicRecordId"):
            output_ref = result.academicRecordId
        elif hasattr(result, "verifierResultId"):
            output_ref = result.verifierResultId
        elif isinstance(result, list) and result and hasattr(result[0], "courseCode"):
            output_ref = result[0].courseCode
        trace.emit(
            "TOOL_RETURNED",
            tool_name=name,
            output_ref=output_ref,
            duration_ms=duration_ms,
        )
        return result

    def _deliver(
        self,
        answer: PlanningAnswer,
        trace: TracePort,
        context: ExecutionContext,
    ) -> PlanningAnswer:
        trace.emit("FINAL_DELIVERED", output_ref=answer.taskId)
        if self._results is not None:
            self._results.save(
                answer=answer,
                events=trace.events,
                manifest=build_run_manifest(
                    context=context, identity=self._run_identity, budget=self._budget
                ),
            )
        return answer

    def _with_fake_model_issue(self, issues: list[Issue]) -> list[Issue]:
        if not isinstance(self._model, FakeModelAdapter):
            return issues
        return [
            *issues,
            Issue(
                code="FAKE_MODEL",
                message="当前是 W2 假模型，不是已配置的模型端点",
                field=None,
                retryable=False,
            ),
        ]

    def _mark_fake_model(self, answer: PlanningAnswer) -> PlanningAnswer:
        marked = self._with_fake_model_issue(list(answer.unknowns))
        if marked == list(answer.unknowns):
            return answer
        return answer.model_copy(update={"unknowns": marked})

    @staticmethod
    def _usage(budget: BudgetTracker, started: datetime) -> Usage:
        return Usage(
            inputTokens=budget.input_tokens,
            outputTokens=budget.output_tokens,
            toolCalls=budget.tool_calls,
            elapsedMs=int((datetime.now(UTC) - started).total_seconds() * 1000),
        )
