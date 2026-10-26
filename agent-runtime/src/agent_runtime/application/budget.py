"""Accumulated run budget and its enforcement (docs/04 section 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class Budget:
    """Single budget entry for enforcement and RunManifest.

    Defaults match docs/04 section 3 and the RunManifest consts in
    ``domain.schema.json``. ``build_run_manifest`` reads this object, so the
    recorded caps stay the ones the runner enforced.
    """

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
    _per_tool: dict[str, int] = field(default_factory=dict)

    def record_tool_call(
        self,
        name: str | None = None,
        tool_caps: dict[str, int] | None = None,
    ) -> None:
        """Count one tool call against the run budget and, when present, the harness cap.

        ``tool_caps is None`` means the caller did not load a tool policy (unit
        tests build a bare snapshot). An empty map means the policy file allows
        no tools. A call past either cap is refused before the HTTP request.
        """
        if tool_caps is not None:
            if not name or name not in tool_caps or self._per_tool.get(name, 0) >= tool_caps[name]:
                raise BudgetExceeded(f"tool_policy 不允许再调用 {name or '未命名工具'}")
            self._per_tool[name] = self._per_tool.get(name, 0) + 1
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
