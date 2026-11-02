"""对话额度：学校进度上下文不能撑爆单次输入预算，会话额度要够用，用完要说清是哪一层额度。

数据全部是虚构的：127 行学校进度树（1 个根、45 个类别、81 个叶子）和 78 门课，
形状与真实导入同量级，名字和编号都是合成的。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from tests.test_advice_chat import ChatTools, _context, _request

from agent_runtime.adapters.model_client import AdviceChatModelReply
from agent_runtime.api.schemas import Course, SchoolProgressImportResult
from agent_runtime.api.settings import Settings
from agent_runtime.application.advice_chat import AdviceChatService
from agent_runtime.application.budget import (
    BudgetExceeded,
    SessionSpendCap,
    SessionSpendLedger,
)

CATEGORIES = [f"类别{i:02d}专业课程组合" for i in range(45)]


def _synthetic_progress(*, all_gaps: bool = True) -> SchoolProgressImportResult:
    now = datetime.now(UTC).isoformat()
    nodes = [
        {
            "nodeId": "node:root",
            "parentId": None,
            "schoolNodeId": "S-ROOT",
            "leaf": False,
            "name": "全校培养方案总计",
            "requiredCredits": 170,
            "earnedCredits": 90,
            "remainingCredits": 80,
        }
    ]
    for i, name in enumerate(CATEGORIES):
        remaining = 5 if all_gaps or i % 3 == 0 else 0
        nodes.append(
            {
                "nodeId": f"node:c{i}",
                "parentId": "node:root",
                "schoolNodeId": f"S-C{i:03d}",
                "leaf": False,
                "name": name,
                "requiredCredits": 10,
                "earnedCredits": 10 - remaining,
                "remainingCredits": remaining,
            }
        )
    for j in range(81):
        i = j % 45
        nodes.append(
            {
                "nodeId": f"node:l{j}",
                "parentId": f"node:c{i}",
                "schoolNodeId": f"S-L{j:03d}",
                "leaf": True,
                "name": f"课程组合{j:03d}选修",
                "requiredCredits": 2,
                "earnedCredits": 1,
                "remainingCredits": 1,
            }
        )
    courses = [
        {
            "nodeId": f"node:l{k % 81}",
            "courseCode": f"SCH{k:05d}",
            "name": f"高等数学与程序设计专题{k:03d}",
            "credits": 3,
            "outcome": "PASSED" if k % 3 else "NOT_TAKEN",
            "completedYear": "2025-2026",
            "completedTerm": "1",
            "grade": None,
            "makeup": None,
            "retake": None,
            "suggestedYear": None,
            "suggestedTerm": None,
        }
        for k in range(78)
    ]
    return SchoolProgressImportResult.model_validate(
        {
            "receipt": {
                "schoolProgressId": "progress:1",
                "contentHash": "c" * 64,
                "importedAt": now,
                "reused": True,
            },
            "snapshot": {
                "format": "coursepilot-shu-academic-progress",
                "version": 1,
                "capturedAt": now,
                "source": "browser adapter",
                "nodes": nodes,
                "courses": courses,
            },
            "academicRecord": {
                "academicRecordId": "record:school",
                "revision": 1,
                "curriculumSnapshotId": "curr:1",
                "completedCourses": [],
                "transcriptComplete": False,
                "sourceKind": "USER_IMPORT",
                "createdAt": now,
            },
        }
    )


def _catalog() -> list[Course]:
    electives = [
        Course(
            courseCode=f"ELC{i:03d}",
            name=f"选修课程名称专题{i:03d}",
            credits=Decimal("2.00"),
            category=CATEGORIES[i % 45],
            sourceRefIds=["src:x"],
            suggestedTerm=None,
        )
        for i in range(120)
    ]
    return electives


class SchoolTools(ChatTools):
    def __init__(self, progress: SchoolProgressImportResult):
        super().__init__()
        self._progress = progress

    def call(self, tool, dto, context, *, params=None, idempotency_key=None):
        if tool == "getSchoolProgress":
            return self._progress
        if tool == "listCourses":
            return _catalog()
        return super().call(tool, dto, context, params=params, idempotency_key=idempotency_key)


class MeasuringModel:
    """Reports input tokens the way the provider would: the real request size, roughly."""

    def __init__(self, output_tokens: int = 1200):
        self.calls = 0
        self.messages: list[dict] = []
        self._output = output_tokens

    def generate_chat(self, *, context, messages):
        self.calls += 1
        self.messages = messages
        size = len(messages[0]["content"].encode("utf-8"))
        return AdviceChatModelReply(
            reply="建议先看看学校还差哪些类别。",
            question=None,
            courses=[],
            suggestions=[],
            input_tokens=size // 3 + 700,
            output_tokens=self._output,
        )


def _model_payload(model: MeasuringModel) -> dict:
    return json.loads(model.messages[-1]["content"])


def test_school_progress_turn_reaches_the_model_within_the_per_call_input_budget() -> None:
    """Before the fix the 127-row tree alone was ~11k estimated tokens, over the 8000 cap.

    The advice service then raised BUDGET_EXCEEDED before any model call, on every turn.
    """
    model = MeasuringModel()
    service = AdviceChatService(tool_client=SchoolTools(_synthetic_progress()), model_adapter=model)

    answer = service.run(_request(), _context())

    assert model.calls == 1
    assert answer.reply
    assert len(model.messages[0]["content"].encode("utf-8")) // 3 < 8000


def test_school_progress_facts_send_counts_and_gaps_not_the_full_tree() -> None:
    model = MeasuringModel()
    service = AdviceChatService(tool_client=SchoolTools(_synthetic_progress()), model_adapter=model)
    service.run(_request(), _context())

    facts = _model_payload(model)
    progress = facts["schoolProgress"]
    assert progress is not None
    # No tree rows, no course list, no school node ids: only counts and unknown items.
    assert "nodes" not in progress and "courses" not in progress
    assert "nodeId" not in json.dumps(progress, ensure_ascii=False)
    assert set(progress["outcomeCounts"]) >= {"PASSED", "NOT_TAKEN"}
    # Gap categories reach the model once, via schoolReportGaps, and only with credits left.
    gaps = facts["schoolReportGaps"]
    assert gaps and len(gaps) <= 45
    assert all(float(item["remainingCredits"]) > 0 for item in gaps)


def test_candidate_courses_sent_to_the_model_are_bounded() -> None:
    model = MeasuringModel()
    service = AdviceChatService(tool_client=SchoolTools(_synthetic_progress()), model_adapter=model)
    service.run(_request(), _context())

    assert len(_model_payload(model)["availableCourses"]) <= 25


def test_chat_history_resent_to_the_model_is_bounded() -> None:
    from agent_runtime.api.schemas.advice_chat import AdviceChatRequest

    long_text = "很长的追问内容" * 200  # about 1400 chars each
    base = _request().model_dump(mode="json")
    base["history"] = [
        {"role": "user" if i % 2 == 0 else "assistant", "text": long_text} for i in range(8)
    ]
    model = MeasuringModel()
    service = AdviceChatService(tool_client=SchoolTools(_synthetic_progress()), model_adapter=model)
    service.run(AdviceChatRequest.model_validate(base), _context())

    history = _model_payload(model)["history"]
    assert len(history) <= 4
    assert all(len(item["text"]) <= 500 for item in history)


def test_ledger_refusal_names_the_exhausted_cap_and_what_a_new_session_resets() -> None:
    cap = SessionSpendCap(max_input_tokens=100, max_output_tokens=100, max_daily_tokens=10_000)
    ledger = SessionSpendLedger(cap)
    ledger.record("session:a", 95, 0)
    with pytest.raises(BudgetExceeded) as session_exc:
        ledger.reserve("session:a", 20, 0)
    assert "会话额度" in str(session_exc.value)
    assert "新建会话" in str(session_exc.value)
    assert "今日全站模型额度已用完" not in str(session_exc.value)

    daily = SessionSpendLedger(SessionSpendCap(max_daily_tokens=100))
    daily.record("session:b", 90, 0)
    with pytest.raises(BudgetExceeded) as daily_exc:
        daily.reserve("session:c", 20, 0)
    assert "今日全站" in str(daily_exc.value)
    assert "新建会话不会重置" in str(daily_exc.value)


def test_default_session_caps_support_ten_chat_turns_and_three_plannings() -> None:
    """Simulate a normal session with the shipped Settings defaults.

    Each chat turn reserves the per-call maximum (8000 in + 4000 out), then settles to
    the usage the model reports. Plannings use the same reservation. The sizes below
    are measured on the synthetic school progress, rounded up, and reflect one
    full-size planning run for each planning (per-run caps are 8000/4000).
    """
    settings = Settings()
    ledger = SessionSpendLedger(
        SessionSpendCap(
            max_input_tokens=settings.session_max_input_tokens,
            max_output_tokens=settings.session_max_output_tokens,
            max_daily_tokens=settings.model_daily_token_cap,
        )
    )
    session = "session:normal"
    model = MeasuringModel(output_tokens=1500)
    service = AdviceChatService(tool_client=SchoolTools(_synthetic_progress()), model_adapter=model)
    from agent_runtime.api.schemas.advice_chat import AdviceChatMessage

    history: list[AdviceChatMessage] = []
    for turn in range(10):
        request = _request().model_copy(
            update={"history": history[-8:], "message": f"第{turn + 1}个问题，推荐课程"}
        )
        reservation = ledger.reserve(session, settings.max_input_tokens, settings.max_output_tokens)
        try:
            answer = service.run(request, _context())
        except Exception:
            reservation.release()
            raise
        reservation.settle(answer.usage.inputTokens, answer.usage.outputTokens)
        history.append(AdviceChatMessage(role="user", text=f"第{turn + 1}个问题"))
        history.append(AdviceChatMessage(role="assistant", text=answer.reply))

    for _ in range(3):
        reservation = ledger.reserve(session, settings.max_input_tokens, settings.max_output_tokens)
        reservation.settle(settings.max_input_tokens, settings.max_output_tokens)

    assert ledger.spent(session)[0] <= settings.session_max_input_tokens
    assert ledger.spent(session)[1] <= settings.session_max_output_tokens


def test_reservation_context_releases_on_any_exit_path() -> None:
    """A failed or cancelled call must not keep its reservation (the old leak path)."""
    ledger = SessionSpendLedger(SessionSpendCap(max_input_tokens=100, max_output_tokens=100))

    with pytest.raises(RuntimeError):
        with ledger.reserve("session:x", 80, 40):
            raise RuntimeError("model call failed without usage")
    assert ledger.spent("session:x") == (0, 0)
    # The held 80 input tokens are gone, so a full-size reservation fits again.
    with ledger.reserve("session:x", 80, 40) as again:
        again.settle(10, 5)
    assert ledger.spent("session:x") == (10, 5)

    with pytest.raises(KeyboardInterrupt):
        with ledger.reserve("session:x", 80, 40):
            raise KeyboardInterrupt
    assert ledger.spent("session:x") == (10, 5)
    with ledger.reserve("session:x", 80, 40) as third:
        third.settle(1, 1)
    assert ledger.spent("session:x") == (11, 6)
