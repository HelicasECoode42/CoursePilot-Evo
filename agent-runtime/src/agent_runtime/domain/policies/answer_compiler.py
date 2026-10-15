"""Assembles PlanningAnswer and Recommendation objects.

The compiler wraps Java verdicts but never alters them: a verdict stays
VALID/INVALID/UNKNOWN exactly as Java returned it (c-agent.md section 2).
"""

from __future__ import annotations

from agent_runtime.api.schemas import (
    AuditResult,
    Issue,
    PlanItem,
    PlanningAnswer,
    PlanValidation,
    Question,
    Recommendation,
    Usage,
)


class AnswerCompiler:
    def clarify(
        self,
        *,
        task_id: str,
        trace_id: str,
        audit: AuditResult,
        question: Question,
        usage: Usage,
    ) -> PlanningAnswer:
        return PlanningAnswer(
            taskId=task_id,
            traceId=trace_id,
            decision="CLARIFY",
            academicAudit=audit,
            recommendations=[],
            clarification=question,
            unknowns=[],
            usage=usage,
        )

    def unable_to_verify(
        self,
        *,
        task_id: str,
        trace_id: str,
        audit: AuditResult,
        issues: list[Issue],
        usage: Usage,
    ) -> PlanningAnswer:
        return PlanningAnswer(
            taskId=task_id,
            traceId=trace_id,
            decision="UNABLE_TO_VERIFY",
            academicAudit=audit,
            recommendations=[],
            clarification=None,
            unknowns=issues,
            usage=usage,
        )

    def recommend(
        self,
        *,
        plan_id: str,
        items: list[PlanItem],
        explanation: str,
        review_note_ids: list[str],
        verdict: PlanValidation,
    ) -> Recommendation:
        # ``verdict`` is passed through unchanged by design.
        return Recommendation(
            planId=plan_id,
            items=items,
            explanation=explanation,
            reviewNoteIds=review_note_ids,
            verification=verdict,
        )
