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
    max_output_tokens: int = 4000
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


@dataclass(frozen=True)
class SessionSpendCap:
    """每个会话的累计 token 上限。

    ``Budget`` 管的是「一次运行」：BudgetTracker 在 PlanningRunner.run 里新建，
    运行结束即丢弃。所以换一个会话、或在同一会话里换一个 Idempotency-Key 再提交，
    预算就从零开始。本类补的是跨请求的那一层：一个会话总共能花多少。

    默认值是单次运行预算（docs/04 第 3 节：input 8000 / output 4000）的 5 倍，
    即一个会话大约可以完整跑 5 次规划。输出预算 2026-10-29 从 2000 调到 4000，
    这里的输出上限同步从 10000 调到 20000，否则「跑 5 次」这个说法就不成立了。
    和 Budget 一样属于部署设置，不是 harness 文件，演化器改不到。
    """

    max_input_tokens: int = 40000
    max_output_tokens: int = 20000
    max_tracked_sessions: int = 10000


class SessionSpendLedger:
    """按会话累计 token 并在超限时拒绝新的运行。

    进程内存实现，和 SessionStore 一样是本地演示用：重启即清空。真实部署需要
    共享存储，否则多实例下每个实例各记一份，上限会被放大到实例数倍。

    ``max_tracked_sessions`` 是内存上限：匿名建会话没有限流，不设上限的话这个
    字典会跟着会话数无限增长。满了之后拒绝新会话的运行，而不是静默丢弃已有记账
    （丢弃等于把花过的钱忘掉，上限就失效了）。
    """

    def __init__(self, cap: SessionSpendCap) -> None:
        self._cap = cap
        self._spent: dict[str, tuple[int, int]] = {}

    def check(self, session_id: str) -> None:
        """在发起运行前调用。已超限、或内存已满且是新会话，都直接拒绝。"""
        spent_in, spent_out = self._spent.get(session_id, (0, 0))
        if spent_in >= self._cap.max_input_tokens:
            raise BudgetExceeded("本会话累计 input token 已达上限，请新建会话")
        if spent_out >= self._cap.max_output_tokens:
            raise BudgetExceeded("本会话累计 output token 已达上限，请新建会话")
        if session_id not in self._spent and len(self._spent) >= self._cap.max_tracked_sessions:
            raise BudgetExceeded("在跟踪的会话数已达上限，暂不接受新会话的规划请求")

    def record(self, session_id: str, input_tokens: int | None, output_tokens: int | None) -> None:
        """运行结束后记账。只在真正跑过模型时调用，幂等回放不重复计费。"""
        if input_tokens is None and output_tokens is None:
            return
        spent_in, spent_out = self._spent.get(session_id, (0, 0))
        self._spent[session_id] = (
            spent_in + (input_tokens or 0),
            spent_out + (output_tokens or 0),
        )

    def spent(self, session_id: str) -> tuple[int, int]:
        """已花的 (input, output)，给测试和排查用。"""
        return self._spent.get(session_id, (0, 0))
