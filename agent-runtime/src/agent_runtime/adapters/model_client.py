"""Controlled model client seam.

W1 ships only the interface; no real model is called yet. The adapter is the
single place allowed to talk to the configured model endpoint (c-agent.md
section 5): a URL found in a message or review is data, never an endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_runtime.api.schemas import PlanItem, Question
from agent_runtime.application.context import ExecutionContext


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
