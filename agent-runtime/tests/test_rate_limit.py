"""建会话限流的行为测试。

这里只测 FixedWindowRateLimiter 自己：窗口内挡住、窗口过去放开、
跟踪的键数量本身有上限。上游 429 的透传在 test_api.py / test_error_handlers.py。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_runtime.api.rate_limit import (
    FixedWindowRateLimiter,
    RateLimit,
    client_rate_key,
)

T0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def _limiter(max_events: int = 3, window_seconds: int = 300, max_tracked_keys: int = 10000):
    return FixedWindowRateLimiter(
        RateLimit(
            max_events=max_events,
            window_seconds=window_seconds,
            max_tracked_keys=max_tracked_keys,
        )
    )


def test_allows_up_to_the_quota_then_rejects() -> None:
    limiter = _limiter(max_events=3)
    assert [limiter.check_and_record("1.2.3.4", now=T0) for _ in range(3)] == [True] * 3
    assert limiter.check_and_record("1.2.3.4", now=T0) is False


def test_a_rejected_call_is_not_recorded() -> None:
    """被拒的调用不能占额度，否则窗口内一直拒就永远拒。"""
    limiter = _limiter(max_events=1)
    assert limiter.check_and_record("1.2.3.4", now=T0) is True
    assert limiter.check_and_record("1.2.3.4", now=T0) is False
    # 第一次 12:00 的记录在 12:04:59 仍在窗口内，所以这里仍然应该拒。
    assert limiter.check_and_record("1.2.3.4", now=T0 + timedelta(seconds=299)) is False
    # 过了 300 秒窗口，只会掉出那一条记录；若刚才的拒绝也被记了，这里就会变成拒。
    assert limiter.check_and_record("1.2.3.4", now=T0 + timedelta(seconds=301)) is True


def test_window_expiry_frees_the_quota() -> None:
    limiter = _limiter(max_events=2, window_seconds=60)
    assert limiter.check_and_record("1.2.3.4", now=T0) is True
    assert limiter.check_and_record("1.2.3.4", now=T0 + timedelta(seconds=30)) is True
    assert limiter.check_and_record("1.2.3.4", now=T0 + timedelta(seconds=40)) is False
    # T0 那条掉出窗口，让出一个额度；T0+30 那条还在。
    assert limiter.check_and_record("1.2.3.4", now=T0 + timedelta(seconds=61)) is True
    assert limiter.check_and_record("1.2.3.4", now=T0 + timedelta(seconds=62)) is False


def test_keys_do_not_share_a_bucket() -> None:
    limiter = _limiter(max_events=1)
    assert limiter.check_and_record("1.2.3.4", now=T0) is True
    assert limiter.check_and_record("5.6.7.8", now=T0) is True
    assert limiter.check_and_record("1.2.3.4", now=T0) is False


def test_tracked_keys_are_capped_so_rotating_keys_cannot_grow_memory() -> None:
    """换 IP 刷也不能把字典撑爆：这是限流本身的内存红线。"""
    limiter = _limiter(max_events=1, window_seconds=60, max_tracked_keys=5)
    for i in range(5):
        assert limiter.check_and_record(f"10.0.0.{i}", now=T0) is True
    assert limiter.tracked_keys() == 5
    # 满了，且没有整桶过期的键可清 → 新键被拒，字典不增长。
    assert limiter.check_and_record("10.0.0.99", now=T0) is False
    assert limiter.tracked_keys() == 5


def test_expired_keys_are_reclaimed_when_the_table_is_full() -> None:
    limiter = _limiter(max_events=1, window_seconds=60, max_tracked_keys=5)
    for i in range(5):
        assert limiter.check_and_record(f"10.0.0.{i}", now=T0) is True
    later = T0 + timedelta(seconds=120)
    # 旧键整桶过期，应被回收，新键放行。
    assert limiter.check_and_record("10.0.0.99", now=later) is True
    assert limiter.tracked_keys() <= 5


# --- 分桶键：CF-Connecting-IP 只在显式信任且对端是回环地址时生效 ---------------------


def test_default_key_is_the_direct_peer_and_ignores_the_cf_header() -> None:
    assert client_rate_key("127.0.0.1", "203.0.113.7", trust_cf_connecting_ip=False) == "127.0.0.1"


def test_trusted_cf_header_is_used_only_when_the_peer_is_loopback() -> None:
    assert client_rate_key("127.0.0.1", "203.0.113.7", trust_cf_connecting_ip=True) == "203.0.113.7"
    assert client_rate_key("::1", "203.0.113.7", trust_cf_connecting_ip=True) == "203.0.113.7"
    # 对端不是回环：说明是直接连进来的，头部可以伪造，必须忽略。
    assert (
        client_rate_key("198.51.100.9", "203.0.113.7", trust_cf_connecting_ip=True)
        == "198.51.100.9"
    )


def test_invalid_cf_header_falls_back_to_the_peer() -> None:
    for bad in ["", "not-an-ip", "203.0.113.7, 10.0.0.1", "x" * 500]:
        assert client_rate_key("127.0.0.1", bad, trust_cf_connecting_ip=True) == "127.0.0.1"


def test_missing_cf_header_falls_back_to_the_peer() -> None:
    assert client_rate_key("127.0.0.1", None, trust_cf_connecting_ip=True) == "127.0.0.1"


def test_cf_header_is_normalised_so_spellings_share_one_bucket() -> None:
    assert (
        client_rate_key("127.0.0.1", " 2001:DB8::1 ", trust_cf_connecting_ip=True) == "2001:db8::1"
    )
