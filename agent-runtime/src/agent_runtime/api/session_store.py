"""In-memory demo session store: only the token hash is kept (docs/04 section 1)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta


class SessionNotFound(Exception):
    """The token is unknown or expired."""


class SessionStoreFull(Exception):
    """存活会话数已达上限。

    过期条目只在同一个令牌再次提交时才被删除（见 resolve），所以废弃的会话会一直
    占着内存。没有这个上限时，建会话这一步可以把进程内存无限撑大。
    """


class SessionStore:
    """Local demo store; a real deployment needs a real identity/session design."""

    def __init__(self, ttl_seconds: int, max_sessions: int = 10000) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_sessions = max_sessions
        self._by_hash: dict[str, tuple[str, datetime]] = {}

    def create(self) -> tuple[str, str, datetime]:
        # 先清掉已过期的，再判上限：过期条目平时没人碰就不会被删，
        # 不先清的话上限会被一堆死会话占满。
        self._sweep_expired()
        if len(self._by_hash) >= self._max_sessions:
            raise SessionStoreFull("存活会话数已达上限")
        token = secrets.token_urlsafe(48)
        session_id = f"session:{uuid.uuid4().hex}"
        expires_at = datetime.now(UTC) + self._ttl
        self._by_hash[self._hash(token)] = (session_id, expires_at)
        return session_id, token, expires_at

    def resolve(self, token: str) -> str:
        entry = self._by_hash.get(self._hash(token))
        if entry is None:
            raise SessionNotFound
        session_id, expires_at = entry
        if datetime.now(UTC) > expires_at:
            self._by_hash.pop(self._hash(token), None)
            raise SessionNotFound
        return session_id

    def _sweep_expired(self) -> None:
        now = datetime.now(UTC)
        for key in [k for k, (_, expires) in self._by_hash.items() if now > expires]:
            self._by_hash.pop(key, None)

    def live_sessions(self) -> int:
        """给测试和排查用。"""
        return len(self._by_hash)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
