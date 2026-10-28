"""每会话累计花费上限（SessionSpendLedger）。

Budget 只管一次运行：BudgetTracker 在 PlanningRunner.run 里新建、运行结束即丢弃。
所以同一个人换一个 Idempotency-Key 再提交，运行预算就从零开始。这里钉住的是跨请求
的那一层，以及它不会把幂等回放重复计费。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.test_api import FakeToolClient, _request_body

from agent_runtime.api.app import create_app
from agent_runtime.application.budget import (
    BudgetExceeded,
    SessionSpendCap,
    SessionSpendLedger,
)


def _ledger(**kw) -> SessionSpendLedger:
    base = {"max_input_tokens": 100, "max_output_tokens": 50, "max_tracked_sessions": 3}
    base.update(kw)
    return SessionSpendLedger(SessionSpendCap(**base))


def test_fresh_session_passes_and_accumulates() -> None:
    led = _ledger()
    led.check("session:a")
    led.record("session:a", 30, 10)
    led.record("session:a", 30, 10)
    assert led.spent("session:a") == (60, 20)
    led.check("session:a")


def test_input_cap_blocks_the_next_run() -> None:
    led = _ledger()
    led.record("session:a", 100, 0)
    with pytest.raises(BudgetExceeded, match="input"):
        led.check("session:a")


def test_output_cap_blocks_the_next_run() -> None:
    led = _ledger()
    led.record("session:a", 0, 50)
    with pytest.raises(BudgetExceeded, match="output"):
        led.check("session:a")


def test_one_session_cap_does_not_block_another() -> None:
    led = _ledger()
    led.record("session:a", 100, 0)
    with pytest.raises(BudgetExceeded):
        led.check("session:a")
    led.check("session:b")


def test_none_usage_is_not_charged() -> None:
    """假模型不报 token。记成 0 才对，不能记成一次满额。"""
    led = _ledger()
    led.record("session:a", None, None)
    assert led.spent("session:a") == (0, 0)
    led.check("session:a")


def test_tracked_session_count_is_bounded() -> None:
    """匿名建会话没有限流，账本不设上限会跟着会话数无限增长。"""
    led = _ledger(max_tracked_sessions=2)
    led.record("session:a", 1, 1)
    led.record("session:b", 1, 1)
    led.check("session:a")  # 已在跟踪的仍然放行
    with pytest.raises(BudgetExceeded, match="会话数"):
        led.check("session:c")


def test_planning_is_refused_once_the_session_cap_is_reached() -> None:
    """路由层接线：超限返回 503 BUDGET_EXCEEDED，复用既有的 BudgetExceeded 处理器。"""
    app = create_app(tool_client=FakeToolClient())
    client = TestClient(app)
    session = client.post("/api/v1/sessions").json()["data"]
    app.state.spend_ledger.record(
        session["sessionId"], app.state.settings.session_max_input_tokens, 0
    )
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {session['sessionToken']}",
            "Idempotency-Key": "spend-1",
            "X-Request-Id": "req:spend-1",
        },
    )
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "ERROR"
    assert body["issues"][0]["code"] == "BUDGET_EXCEEDED"


def test_replay_of_an_earlier_answer_is_not_refused() -> None:
    """幂等回放没有新花费，不该被上限挡住，也不该被重复计费。"""
    app = create_app(tool_client=FakeToolClient())
    client = TestClient(app)
    session = client.post("/api/v1/sessions").json()["data"]
    headers = {
        "Authorization": f"Bearer {session['sessionToken']}",
        "Idempotency-Key": "spend-2",
        "X-Request-Id": "req:spend-2",
    }
    first = client.post("/api/v1/planning", json=_request_body(), headers=headers)
    assert first.status_code == 200

    # 第一次之后把账本顶满：同键重提必须仍然拿到原答复。
    app.state.spend_ledger.record(
        session["sessionId"], app.state.settings.session_max_input_tokens, 0
    )
    replay = client.post("/api/v1/planning", json=_request_body(), headers=headers)
    assert replay.status_code == 200
    assert replay.json()["data"] == first.json()["data"]

    # 但换一个键就是新运行，必须被挡住。
    fresh = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={**headers, "Idempotency-Key": "spend-3", "X-Request-Id": "req:spend-3"},
    )
    assert fresh.status_code == 503
    assert fresh.json()["issues"][0]["code"] == "BUDGET_EXCEEDED"
