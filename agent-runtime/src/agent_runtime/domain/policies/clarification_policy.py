"""Builds a single concrete Question when the runner must clarify."""

from __future__ import annotations

from agent_runtime.api.schemas import Choice, Question
from agent_runtime.domain.policies.intent_resolver import ResolvedIntent


class ClarificationPolicy:
    """Maps a missing-goal resolution to one actionable Question (C-02/C-03)."""

    def build_question(self, resolved: ResolvedIntent) -> Question:
        if "teacher_vs_schedule" in resolved.missing:
            return Question(
                questionId="tradeoff:teacher-vs-schedule",
                text="指定教师和必须避开的上课时间可能冲突。请先保证哪一项，另一项作为次要条件。",
                choices=[
                    Choice(value="KEEP_TEACHER", label="先保留指定教师"),
                    Choice(value="KEEP_SCHEDULE", label="先保证硬时间"),
                ],
                allowFreeText=False,
                requiredFor=["teacher_vs_schedule"],
            )
        return Question(
            questionId="goal:missing",
            text="请补充你的选课目标（例如：高绩点、少签到、指定老师等）。",
            choices=[],
            allowFreeText=True,
            requiredFor=list(resolved.missing),
        )
