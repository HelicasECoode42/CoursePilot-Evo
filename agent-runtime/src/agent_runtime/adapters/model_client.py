"""Controlled model client seam.

The adapter is the only place allowed to talk to the configured model endpoint
(c-agent.md section 5): a URL found in a message or review is data, never an
endpoint. W2 ships a typed fake that only proposes ids already returned by tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from agent_runtime.api.schemas import PlanItem, Question
from agent_runtime.application.context import ExecutionContext
from agent_runtime.domain.policies.candidate_guard import KnownFacts

FACTS_MESSAGE_PREFIX = "AVAILABLE_FACTS:"


class ModelInvalidOutput(RuntimeError):
    """Provider returned unusable JSON / empty candidates (-> limited one repair)."""


@dataclass(frozen=True)
class ModelReply:
    """Provider-agnostic model result: either a clarification or candidate items."""

    clarify: Question | None = None
    items: list[PlanItem] | None = None


class ModelAdapter(Protocol):
    """OpenAI-compatible, provider-agnostic generate entry point.

    Implementations must honour the remaining budget/timeout and must not enable
    automatic provider retries (docs/04 section 3).
    """

    def generate(
        self,
        *,
        context: ExecutionContext,
        messages: list[dict[str, str]],
        tool_schemas: list[dict],
    ) -> ModelReply: ...


def facts_from_messages(messages: list[dict[str, str]]) -> KnownFacts:
    """Read the bounded id set the runner stuffed into the last facts message."""
    for message in reversed(messages):
        content = message.get("content", "")
        if not content.startswith(FACTS_MESSAGE_PREFIX):
            continue
        raw = json.loads(content[len(FACTS_MESSAGE_PREFIX) :])
        return KnownFacts(
            course_codes=frozenset(raw.get("courseCodes", [])),
            teacher_keys=frozenset(raw.get("teacherKeys", [])),
            class_ids=frozenset(raw.get("classIds", [])),
        )
    return KnownFacts()


class FakeModelAdapter:
    """Deterministic W2 stand-in: pick tool-provided courses, never invent ids.

    This is not a real Agent. Production still needs a configured model endpoint.
    """

    def __init__(self, *, fail_times: int = 0) -> None:
        self._fail_times = fail_times

    def generate(
        self,
        *,
        context: ExecutionContext,
        messages: list[dict[str, str]],
        tool_schemas: list[dict],
    ) -> ModelReply:
        del context, tool_schemas
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ModelInvalidOutput("模型输出不是可用的候选 JSON")
        facts = facts_from_messages(messages)
        if not facts.course_codes:
            return ModelReply(items=None)
        items = [
            PlanItem(courseCode=code, teacherKey=None, classId=None)
            for code in sorted(facts.course_codes)[:3]
        ]
        return ModelReply(items=items)
