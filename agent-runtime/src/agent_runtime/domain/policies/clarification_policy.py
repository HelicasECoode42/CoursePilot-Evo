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
                text="请确定指定教师与必须避开的上课时间的考虑顺序；两项硬条件都会保留，若两者冲突，仍需调整后再提交。",
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
