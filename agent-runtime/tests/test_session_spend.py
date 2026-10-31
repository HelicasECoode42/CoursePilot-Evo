"""累计花费上限（SessionSpendLedger）：预留、结算、每会话与每日上限。

Budget 只管一次运行：BudgetTracker 在 PlanningRunner.run 里新建、运行结束即丢弃。
所以同一个人换一个 Idempotency-Key 再提交，运行预算就从零开始。这里钉住的是跨请求
的那一层：并发请求不能同时通过检查（原子预留），失败不计入也不占额度，幂等回放不重复计费，
以及进程级的每日上限。
"""

from __future__ import annotations

import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from tests.test_api import FakeToolClient, _request_body

from agent_runtime.adapters.tool_client import ToolUnavailable
from agent_runtime.api.app import create_app
from agent_runtime.api.settings import Settings
from agent_runtime.application.budget import (
    BudgetExceeded,
    SessionSpendCap,
    SessionSpendLedger,
)

DAY = date(2026, 10, 30)


def _ledger(today=None, **kw) -> SessionSpendLedger:
    base = {
        "max_input_tokens": 100,
        "max_output_tokens": 50,
        "max_tracked_sessions": 3,
        "max_daily_tokens": 1000,
    }
    base.update(kw)
    return SessionSpendLedger(SessionSpendCap(**base), today=today or (lambda: DAY))


def test_settle_replaces_the_reservation_with_actual_usage() -> None:
    led = _ledger()
    led.reserve("session:a", 60, 20).settle(30, 10)
    assert led.spent("session:a") == (30, 10)
    # 预留的 60/20 已经释放，只剩实际的 30/10 占额度，所以第二次预留仍然放行。
    led.reserve("session:a", 60, 20).settle(30, 10)
    assert led.spent("session:a") == (60, 20)


def test_refused_reservation_leaves_nothing_behind() -> None:
    led = _ledger()
    led.record("session:a", 50, 0)
    with pytest.raises(BudgetExceeded, match="input"):
        led.reserve("session:a", 60, 0)
    # 被拒的预留不能占额度：同样的会话，刚好够的请求仍然放行。
    led.reserve("session:a", 50, 0).release()


def test_output_cap_refuses_at_reservation_time() -> None:
    led = _ledger()
    led.record("session:a", 0, 40)
    with pytest.raises(BudgetExceeded, match="output"):
        led.reserve("session:a", 0, 20)


def test_in_flight_reservation_counts_against_a_concurrent_request() -> None:
    """第一个请求还没结算时，同一会话的第二个请求必须看到它占着的额度。"""
    led = _ledger()
    first = led.reserve("session:a", 60, 0)
    with pytest.raises(BudgetExceeded, match="input"):
        led.reserve("session:a", 60, 0)
    first.settle(10, 0)
    led.reserve("session:a", 60, 0).release()


def test_concurrent_reserves_cannot_overshoot_the_session_cap() -> None:
    """并发提交：检查和预留必须在同一把锁里，否则多个线程会同时通过检查。"""
    led = _ledger(max_daily_tokens=10_000_000)
    workers = 40
    barrier = threading.Barrier(workers)
    granted: list[object] = []
    refused: list[Exception] = []
    guard = threading.Lock()

    def attempt() -> None:
        barrier.wait()
        try:
            reservation = led.reserve("session:a", 10, 0)
        except BudgetExceeded as exc:
            with guard:
                refused.append(exc)
        else:
            with guard:
                granted.append(reservation)

    threads = [threading.Thread(target=attempt) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # 输入上限 100，每次预留 10：恰好 10 次通过，其余 30 次被拒。
    assert len(granted) == 10
    assert len(refused) == workers - 10


def test_release_on_failure_frees_the_reservation() -> None:
    led = _ledger()
    led.reserve("session:a", 100, 0).release()
    assert led.spent("session:a") == (0, 0)
    led.reserve("session:a", 100, 0).release()


def test_settle_only_takes_effect_once() -> None:
    led = _ledger()
    reservation = led.reserve("session:a", 10, 5)
    reservation.settle(10, 5)
    reservation.settle(99, 99)
    reservation.release()
    assert led.spent("session:a") == (10, 5)


def test_missing_usage_is_not_charged_as_a_full_reservation() -> None:
    """假模型不报 token。记成 0 才对，不能记成一次满额。"""
    led = _ledger()
    led.reserve("session:a", 10, 5).settle(None, None)
    assert led.spent("session:a") == (0, 0)


def test_one_session_cap_does_not_block_another() -> None:
    led = _ledger()
    led.record("session:a", 100, 0)
    with pytest.raises(BudgetExceeded):
        led.reserve("session:a", 1, 0)
    led.reserve("session:b", 1, 0).release()


def test_tracked_session_count_is_bounded() -> None:
    """匿名建会话没有限流，账本不设上限会跟着会话数无限增长。"""
    led = _ledger(max_tracked_sessions=2)
    led.reserve("session:a", 1, 1).settle(1, 1)
    led.reserve("session:b", 1, 1).settle(1, 1)
    led.reserve("session:a", 1, 1).release()  # 已在跟踪的仍然放行
    with pytest.raises(BudgetExceeded, match="会话数"):
        led.reserve("session:c", 1, 1)


def test_daily_cap_is_shared_across_sessions() -> None:
    led = _ledger(max_daily_tokens=100)
    led.reserve("session:a", 60, 0).settle(60, 0)
    led.reserve("session:b", 30, 0).settle(30, 0)
    with pytest.raises(BudgetExceeded, match="全局上限"):
        led.reserve("session:c", 20, 0)
    assert led.daily_used() == 90


def test_in_flight_reservations_count_against_the_daily_cap() -> None:
    led = _ledger(max_daily_tokens=100)
    held = led.reserve("session:a", 100, 0)
    with pytest.raises(BudgetExceeded, match="全局上限"):
        led.reserve("session:b", 1, 0)
    held.release()
    led.reserve("session:b", 1, 0).release()


def test_daily_cap_resets_on_the_next_utc_day() -> None:
    today = [DAY]
    led = _ledger(today=lambda: today[0], max_daily_tokens=100)
    led.reserve("session:a", 100, 0).settle(100, 0)
    with pytest.raises(BudgetExceeded, match="全局上限"):
        led.reserve("session:b", 1, 0)
    today[0] = date(2026, 10, 31)
    led.reserve("session:b", 100, 0).settle(100, 0)
    assert led.daily_used() == 100


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


def test_planning_is_refused_by_the_process_wide_daily_cap() -> None:
    app = create_app(Settings(model_daily_token_cap=1), tool_client=FakeToolClient())
    client = TestClient(app)
    session = client.post("/api/v1/sessions").json()["data"]
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {session['sessionToken']}",
            "Idempotency-Key": "daily-1",
            "X-Request-Id": "req:daily-1",
        },
    )
    assert response.status_code == 503
    assert response.json()["issues"][0]["code"] == "BUDGET_EXCEEDED"


def test_failed_run_releases_its_reservation() -> None:
    """运行失败且没有实际用量：预留整笔释放，不能把额度永久占住。"""

    class FailingRunner:
        def run(self, request, context):
            raise ToolUnavailable("java down")

    app = create_app(tool_client=FakeToolClient(), runner=FailingRunner())
    client = TestClient(app)
    session = client.post("/api/v1/sessions").json()["data"]
    response = client.post(
        "/api/v1/planning",
        json=_request_body(),
        headers={
            "Authorization": f"Bearer {session['sessionToken']}",
            "Idempotency-Key": "fail-1",
            "X-Request-Id": "req:fail-1",
        },
    )
    assert response.status_code == 503
    assert app.state.spend_ledger.spent(session["sessionId"]) == (0, 0)
    settings = app.state.settings
    app.state.spend_ledger.reserve(
        session["sessionId"], settings.session_max_input_tokens, settings.session_max_output_tokens
    ).release()


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
