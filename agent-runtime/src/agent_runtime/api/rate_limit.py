"""建会话的限流：固定窗口计数，按调用方地址分桶。

为什么需要：POST /api/v1/sessions 不要认证也没有配额，而每建一个会话，
SessionStore、IdempotencyStore、SessionPlanStore 都会在进程内存里多一条且不会自动清理。
不限流的话，一个循环就能把内存撑爆，网页对所有人都打不开。

分桶键见 client_rate_key：默认是直连对端地址。放在同机反向代理（cloudflared、Vite 代理）
后面时对端总是 127.0.0.1，整个限流会退化成一个全局配额。CP_TRUST_CF_CONNECTING_IP=true
时，对端是回环地址才改用 CF-Connecting-IP 分桶，这样每个访客才有自己的配额。
真正的按人限流仍需要可信的调用方身份，而建会话这一步恰恰还没有身份。
"""

from __future__ import annotations

import ipaddress
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class RateLimit:
    """固定窗口配额。默认值：五分钟内同一地址最多建 10 个会话。"""

    max_events: int = 10
    window_seconds: int = 300
    max_tracked_keys: int = 10000


@dataclass
class FixedWindowRateLimiter:
    """按键记录最近一个窗口内的事件时间，超额即拒绝。

    不做令牌桶也不做滑动平均：这里要的是「挡住脚本循环」，固定窗口足够，
    而且行为可预测、好解释给用户听（「五分钟内最多 10 次」）。
    """

    limit: RateLimit
    _events: dict[str, deque[datetime]] = field(default_factory=dict)

    def check_and_record(self, key: str, *, now: datetime | None = None) -> bool:
        """放行返回 True 并记一次；超额返回 False 且不记。"""
        moment = now or datetime.now(UTC)
        cutoff = moment - timedelta(seconds=self.limit.window_seconds)
        bucket = self._events.get(key)
        if bucket is None:
            # 跟踪的键本身也要有上限，否则换 IP 刷同样能把这个字典撑爆。
            # 满了之后先清掉已经整桶过期的键，还是满就拒绝新键。
            if len(self._events) >= self.limit.max_tracked_keys:
                self._drop_expired(cutoff)
            if len(self._events) >= self.limit.max_tracked_keys:
                return False
            bucket = deque()
            self._events[key] = bucket
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit.max_events:
            return False
        bucket.append(moment)
        return True

    def _drop_expired(self, cutoff: datetime) -> None:
        for key in [k for k, v in self._events.items() if not v or v[-1] < cutoff]:
            self._events.pop(key, None)

    def tracked_keys(self) -> int:
        """给测试和排查用。"""
        return len(self._events)


def client_rate_key(
    peer_host: str | None,
    cf_connecting_ip: str | None,
    *,
    trust_cf_connecting_ip: bool,
) -> str:
    """决定限流分桶用哪个地址。

    - 默认（或未开启信任）：直连对端地址。
    - 开启信任且对端是回环地址（说明请求来自同机代理）：用 CF-Connecting-IP，但必须是
      合法 IP 字面量，否则退回对端地址。规范化后再返回，避免同一地址写法不同被拆成两桶。
    - 从不读取 X-Forwarded-For：它可以被任何客户端伪造。
    """
    peer = peer_host or "unknown"
    if not trust_cf_connecting_ip or not _is_loopback(peer) or cf_connecting_ip is None:
        return peer
    try:
        return str(ipaddress.ip_address(cf_connecting_ip.strip()))
    except ValueError:
        return peer


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
