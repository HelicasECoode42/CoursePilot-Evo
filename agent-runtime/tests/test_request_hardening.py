"""请求进入应用前后的两道加固：请求体大小上限，以及建会话限流的分桶键（路由层）。

纯函数层面的分桶规则在 test_rate_limit.py，这里只测接线：中间件是否真的在读取请求体前后
生效，路由是否真的按 CP_TRUST_CF_CONNECTING_IP 选择分桶键。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.test_api import FakeToolClient

from agent_runtime.api.app import create_app
from agent_runtime.api.settings import Settings

LIMIT = 256


def _client(**settings) -> TestClient:
    app = create_app(Settings(max_body_bytes=LIMIT, **settings), tool_client=FakeToolClient())
    return TestClient(app)


def _planning_headers() -> dict[str, str]:
    return {"Idempotency-Key": "size-1", "X-Request-Id": "req:size-1"}


def test_declared_length_over_the_limit_is_rejected_with_the_error_envelope() -> None:
    client = _client()
    response = client.post(
        "/api/v1/planning",
        content=b"{" + b" " * (LIMIT + 10) + b"}",
        headers={"Content-Type": "application/json", **_planning_headers()},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["status"] == "INVALID_INPUT"
    assert body["issues"][0]["code"] == "INVALID_INPUT"
    assert body["issues"][0]["retryable"] is False


def test_streamed_body_over_the_limit_is_rejected_without_content_length() -> None:
    """分块传输没有声明长度，必须边读边数。超过就是 413，而且不交给路由处理。"""
    client = _client()

    def chunks():
        for _ in range(10):
            yield b" " * 64

    response = client.post(
        "/api/v1/planning",
        content=chunks(),
        headers={"Content-Type": "application/json", **_planning_headers()},
    )
    assert response.status_code == 413
    assert response.json()["issues"][0]["code"] == "INVALID_INPUT"


def test_request_under_the_limit_reaches_the_route() -> None:
    """没有会话令牌，所以路由会返回 401：说明请求体通过了大小检查，进入了路由。"""
    client = _client()
    response = client.post(
        "/api/v1/planning",
        content=b"{}",
        headers={"Content-Type": "application/json", **_planning_headers()},
    )
    assert response.status_code == 401


def test_body_limit_applies_before_authentication() -> None:
    """超限的请求体在鉴权之前就被拒绝，未认证的人也不能用大请求占内存。"""
    client = _client()
    response = client.post(
        "/api/v1/planning",
        content=b" " * (LIMIT * 4),
        headers={"Content-Type": "application/json", **_planning_headers()},
    )
    assert response.status_code == 413


def test_session_rate_limit_uses_the_direct_peer_by_default() -> None:
    """默认不信任 CF-Connecting-IP：即使是回环对端，头部不同也仍共用同一个桶。"""
    client = TestClient(
        create_app(
            Settings(session_rate_limit_max=1, trust_cf_connecting_ip=False),
            tool_client=FakeToolClient(),
        ),
        client=("127.0.0.1", 50000),
    )
    assert (
        client.post("/api/v1/sessions", headers={"CF-Connecting-IP": "203.0.113.1"}).status_code
        == 201
    )
    assert (
        client.post("/api/v1/sessions", headers={"CF-Connecting-IP": "203.0.113.2"}).status_code
        == 429
    )


def test_session_rate_limit_keys_on_cf_connecting_ip_when_trusted() -> None:
    """同机代理（回环对端）且显式信任：每个访客用自己的 CF-Connecting-IP 分桶。"""
    client = TestClient(
        create_app(
            Settings(session_rate_limit_max=1, trust_cf_connecting_ip=True),
            tool_client=FakeToolClient(),
        ),
        client=("127.0.0.1", 50000),
    )
    assert (
        client.post("/api/v1/sessions", headers={"CF-Connecting-IP": "203.0.113.1"}).status_code
        == 201
    )
    assert (
        client.post("/api/v1/sessions", headers={"CF-Connecting-IP": "203.0.113.1"}).status_code
        == 429
    )
    assert (
        client.post("/api/v1/sessions", headers={"CF-Connecting-IP": "203.0.113.2"}).status_code
        == 201
    )


def test_cf_header_is_ignored_when_the_peer_is_not_loopback() -> None:
    """直连（非回环）的请求可以随意伪造 CF-Connecting-IP，因此必须忽略。"""
    client = TestClient(
        create_app(
            Settings(session_rate_limit_max=1, trust_cf_connecting_ip=True),
            tool_client=FakeToolClient(),
        ),
        client=("198.51.100.9", 50000),
    )
    assert (
        client.post("/api/v1/sessions", headers={"CF-Connecting-IP": "203.0.113.1"}).status_code
        == 201
    )
    assert (
        client.post("/api/v1/sessions", headers={"CF-Connecting-IP": "203.0.113.2"}).status_code
        == 429
    )
