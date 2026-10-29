"""建会话的限流：固定窗口计数，按调用方地址分桶。

为什么需要：POST /api/v1/sessions 不要认证也没有配额，而每建一个会话，
SessionStore、IdempotencyStore、SessionPlanStore 都会在进程内存里多一条且不会自动清理。
不限流的话，一个循环就能把内存撑爆，网页对所有人都打不开。

局限（必须知道，不要当成按人限流）：分桶键是 request.client.host。放在反向代理
后面时它是代理的地址，于是整个限流退化成一个全局配额——所有人共享同一个桶。
真正的按人限流需要可信的调用方身份，而建会话这一步恰恰还没有身份。
"""

from __future__ import annotations

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
