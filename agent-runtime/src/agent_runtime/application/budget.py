"""Accumulated run budget and its enforcement (docs/04 section 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class Budget:
    """Default caps: 8000/2000 tokens, 6 tools, 3 model calls, 45 s."""

    max_input_tokens: int = 8000
    max_output_tokens: int = 2000
    max_tool_calls: int = 6
    max_model_calls: int = 3
    deadline_ms: int = 45000


class BudgetExceeded(RuntimeError):
    """Raised when a run exceeds its configured budget (c-agent.md section 6)."""


@dataclass
class BudgetTracker:
    budget: Budget
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: int = 0
    model_calls: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def record_tool_call(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.budget.max_tool_calls:
            raise BudgetExceeded("maxToolCalls exceeded")

    def record_model_call(self) -> None:
        self.model_calls += 1
        if self.model_calls > self.budget.max_model_calls:
            raise BudgetExceeded("maxModelCalls exceeded")

    def record_tokens(self, input_tokens: int | None, output_tokens: int | None) -> None:
        if input_tokens is None and output_tokens is None:
            return
        if input_tokens is not None:
            self.input_tokens = (self.input_tokens or 0) + input_tokens
            if self.input_tokens > self.budget.max_input_tokens:
                raise BudgetExceeded("maxInputTokens exceeded")
        if output_tokens is not None:
            self.output_tokens = (self.output_tokens or 0) + output_tokens
            if self.output_tokens > self.budget.max_output_tokens:
                raise BudgetExceeded("maxOutputTokens exceeded")

    def check_deadline(self) -> None:
        elapsed_ms = int((datetime.now(UTC) - self.started_at).total_seconds() * 1000)
        if elapsed_ms > self.budget.deadline_ms:
            raise BudgetExceeded("deadline exceeded")
