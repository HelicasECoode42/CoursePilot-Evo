"""Builds a single concrete Question when the runner must clarify."""

from __future__ import annotations

from agent_runtime.api.schemas import Question
from agent_runtime.domain.policies.intent_resolver import ResolvedIntent


class ClarificationPolicy:
    """Maps a missing-goal resolution to one actionable Question (C-02)."""

    def build_question(self, resolved: ResolvedIntent) -> Question:
        return Question(
            questionId="goal:missing",
            text="请补充你的选课目标（例如：高绩点、少签到、指定老师等）。",
            choices=[],
            allowFreeText=True,
            requiredFor=list(resolved.missing),
        )
