"""Accumulated run budget and its enforcement (docs/04 section 3)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime


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
    """会话与进程级的累计 token 上限。

    ``Budget`` 管的是「一次运行」：BudgetTracker 在 PlanningRunner.run 里新建，
    运行结束即丢弃。所以换一个会话、或在同一会话里换一个 Idempotency-Key 再提交，
    预算就从零开始。这里补的是跨请求的两层：

    - 每会话累计上限（max_input_tokens / max_output_tokens）：一个会话总共能花多少。
    - 进程级每日总量（max_daily_tokens，input 与 output 合计）：所有会话加起来的上限，
      挡住「多开会话」绕过每会话上限的情况。

    这里的类默认值只在直接构造 SessionSpendCap 时生效。应用实际使用的是 Settings：
    CP_SESSION_MAX_OUTPUT_TOKENS 默认 10000（不是这里的 20000），CP_SESSION_MAX_INPUT_TOKENS
    默认 40000（单次运行输入预算 8000 的 5 倍），CP_MODEL_DAILY_TOKEN_CAP 默认 1000000。
    和 Budget 一样属于部署设置，不是 harness 文件，演化器改不到。
    """

    max_input_tokens: int = 40000
    max_output_tokens: int = 20000
    max_tracked_sessions: int = 10000
    max_daily_tokens: int = 1_000_000


class SpendReservation:
    """一笔尚未结算的预留。settle / release 只生效一次，重复调用无害。"""

    def __init__(
        self,
        ledger: SessionSpendLedger,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self._ledger = ledger
        self._session_id = session_id
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._open = True

    def settle(self, input_tokens: int | None, output_tokens: int | None) -> None:
        """用实际用量替换预留。两个都是 None 表示没有可记的用量，等同于 release。"""
        if not self._open:
            return
        self._open = False
        self._ledger._settle(
            self._session_id,
            self._input_tokens,
            self._output_tokens,
            input_tokens,
            output_tokens,
        )

    def release(self) -> None:
        """调用失败且没有实际用量时整笔释放。"""
        self.settle(None, None)


class SessionSpendLedger:
    """按会话和进程累计 token，并在运行前原子地预留上限。

    用法：运行前 ``reserve``，按单次运行的最大可能用量预留。检查和预留在同一把锁里完成，
    所以并发请求不会同时通过检查。模型调用结束后 ``settle`` 成实际用量；失败时，异常上带了
    实际用量就按它结算，否则 ``release`` 整笔释放。

    进程内存实现，和 SessionStore 一样是本地演示用：重启即清空。真实部署需要
    共享存储，否则多实例下每个实例各记一份，上限会被放大到实例数倍。

    ``max_tracked_sessions`` 是内存上限：匿名建会话没有限流，不设上限的话这个
    字典会跟着会话数无限增长。满了之后拒绝新会话的运行，而不是静默丢弃已有记账
    （丢弃等于把花过的钱忘掉，上限就失效了）。
    """

    def __init__(
        self,
        cap: SessionSpendCap,
        *,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._cap = cap
        self._today = today or (lambda: datetime.now(UTC).date())
        self._lock = threading.Lock()
        self._spent: dict[str, tuple[int, int]] = {}
        self._inflight: dict[str, tuple[int, int]] = {}
        self._day: date | None = None
        self._daily_used = 0
        self._daily_inflight = 0

    def reserve(self, session_id: str, input_tokens: int, output_tokens: int) -> SpendReservation:
        """检查并预留。超限，或内存已满且是新会话时直接拒绝，且不留下任何预留。"""
        with self._lock:
            self._roll_day()
            spent_in, spent_out = self._spent.get(session_id, (0, 0))
            fly_in, fly_out = self._inflight.get(session_id, (0, 0))
            if spent_in + fly_in + input_tokens > self._cap.max_input_tokens:
                raise BudgetExceeded("本会话累计 input token 已达上限，请新建会话")
            if spent_out + fly_out + output_tokens > self._cap.max_output_tokens:
                raise BudgetExceeded("本会话累计 output token 已达上限，请新建会话")
            if session_id not in self._spent and len(self._spent) >= self._cap.max_tracked_sessions:
                raise BudgetExceeded("在跟踪的会话数已达上限，暂不接受新会话的规划请求")
            total = input_tokens + output_tokens
            if self._daily_used + self._daily_inflight + total > self._cap.max_daily_tokens:
                raise BudgetExceeded("今日模型用量已达全局上限，请明天再试")
            self._spent.setdefault(session_id, (0, 0))
            self._inflight[session_id] = (fly_in + input_tokens, fly_out + output_tokens)
            self._daily_inflight += total
            return SpendReservation(self, session_id, input_tokens, output_tokens)

    def record(self, session_id: str, input_tokens: int | None, output_tokens: int | None) -> None:
        """不经预留直接记账，只给测试和排查用。运行路径请用 reserve 与 settle。"""
        with self._lock:
            self._roll_day()
            self._charge(session_id, input_tokens, output_tokens)

    def spent(self, session_id: str) -> tuple[int, int]:
        """已结算的 (input, output)，给测试和排查用。不含未结算的预留。"""
        with self._lock:
            return self._spent.get(session_id, (0, 0))

    def daily_used(self) -> int:
        """今天（UTC）已结算的 input 与 output 合计，给测试和排查用。"""
        with self._lock:
            self._roll_day()
            return self._daily_used

    def _settle(
        self,
        session_id: str,
        reserved_in: int,
        reserved_out: int,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        with self._lock:
            self._roll_day()
            fly_in, fly_out = self._inflight.get(session_id, (0, 0))
            left = (fly_in - reserved_in, fly_out - reserved_out)
            if left == (0, 0):
                self._inflight.pop(session_id, None)
            else:
                self._inflight[session_id] = left
            self._daily_inflight -= reserved_in + reserved_out
            self._charge(session_id, input_tokens, output_tokens)

    def _charge(self, session_id: str, input_tokens: int | None, output_tokens: int | None) -> None:
        """记账。None 表示没有可记的用量（例如假模型不报 token），不记。调用方须持有锁。"""
        if input_tokens is None and output_tokens is None:
            return
        spent_in, spent_out = self._spent.get(session_id, (0, 0))
        self._spent[session_id] = (
            spent_in + (input_tokens or 0),
            spent_out + (output_tokens or 0),
        )
        self._daily_used += (input_tokens or 0) + (output_tokens or 0)

    def _roll_day(self) -> None:
        """UTC 日期变化时清零当日已用量。仍在途的预留保留，结算时从中扣除。调用方须持有锁。"""
        today = self._today()
        if today != self._day:
            self._day = today
            self._daily_used = 0
