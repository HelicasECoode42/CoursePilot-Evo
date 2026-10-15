"""The single Planning Runner shared by production and the benchmark."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from agent_runtime.adapters.harness_loader import HarnessSnapshot
from agent_runtime.adapters.model_client import ModelAdapter
from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.adapters.trace_port import TracePort
from agent_runtime.api.schemas import (
    AuditRequest,
    AuditResult,
    Issue,
    PlanningAnswer,
    PlanningRequest,
    Usage,
)
from agent_runtime.application.budget import Budget, BudgetTracker
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import digest, new_id
from agent_runtime.domain.policies.answer_compiler import AnswerCompiler
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
    ) -> None:
        self._tools = tool_client
        self._harness = harness
        self._model = model_adapter  # W2/W3 seam; unused in the W1 clarify-only flow
        self._intent_resolver = intent_resolver or IntentResolver()
        self._clarification = clarification_policy or ClarificationPolicy()
        self._answer = answer_compiler or AnswerCompiler()

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
        budget = BudgetTracker(Budget())
        started = datetime.now(UTC)

        trace.emit("USER_INPUT", input_digest=digest(request.promptText))

        resolved = self._intent_resolver.resolve(request)
        trace.emit("GOAL_EXTRACTED", input_digest=digest(request.promptText))

        # Hard facts come from Java first, even before a clarification (C-05).
        budget.record_tool_call()
        budget.check_deadline()
        audit = cast(
            AuditResult,
            self._tools.call(
                "auditRequirements",
                AuditRequest(
                    schemaVersion="1.0",
                    curriculumSnapshotId=request.curriculumSnapshotId,
                    academicRecordId=request.academicRecordId,
                ),
                context,
            ),
        )
        trace.emit("TOOL_CALLED", tool_name="auditRequirements")
        trace.emit(
            "TOOL_RETURNED", tool_name="auditRequirements", output_ref=audit.academicRecordId
        )

        usage = Usage(
            inputTokens=None,
            outputTokens=None,
            toolCalls=budget.tool_calls,
            elapsedMs=int((datetime.now(UTC) - started).total_seconds() * 1000),
        )

        if resolved.needs_clarification:
            question = self._clarification.build_question(resolved)
            trace.emit("CLARIFICATION_REQUESTED", output_ref=question.questionId)
            answer = self._answer.clarify(
                task_id=task_id, trace_id=trace_id, audit=audit, question=question, usage=usage
            )
        else:
            # W2/W3: propose via model -> guard -> validate -> compile. The W1
            # skeleton has no real Agent, so report that honestly instead of
            # fabricating a recommendation (c-agent.md section 7).
            answer = self._answer.unable_to_verify(
                task_id=task_id,
                trace_id=trace_id,
                audit=audit,
                issues=[
                    Issue(
                        code="PLANNING_LOOP_PENDING",
                        message="规划循环尚未实现（W2/W3）",
                        field=None,
                        retryable=False,
                    )
                ],
                usage=usage,
            )

        trace.emit("FINAL_DELIVERED", output_ref=answer.taskId)
        return answer
