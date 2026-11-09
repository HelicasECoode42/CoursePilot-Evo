"""In-memory demo session store: only the token hash is kept (docs/04 section 1)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from threading import Lock


class SessionNotFound(Exception):
    """The token is unknown or expired."""


class SessionStoreFull(Exception):
    """存活会话数已达上限。"""


class SessionStore:
    """Local demo store; a real deployment needs a real identity/session design."""

    def __init__(self, ttl_seconds: int, max_sessions: int = 10000) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_sessions = max_sessions
        self._lock = Lock()
        self._by_hash: dict[str, tuple[str, datetime]] = {}
        self._expired_session_ids: set[str] = set()

    def create(self) -> tuple[str, str, datetime]:
        with self._lock:
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
        with self._lock:
            entry = self._by_hash.get(self._hash(token))
            if entry is None:
                raise SessionNotFound
            session_id, expires_at = entry
            if datetime.now(UTC) > expires_at:
                self._by_hash.pop(self._hash(token), None)
                self._expired_session_ids.add(session_id)
                raise SessionNotFound
            return session_id

    def _sweep_expired(self) -> None:
        now = datetime.now(UTC)
        for key in [k for k, (_, expires) in self._by_hash.items() if now > expires]:
            session_id, _ = self._by_hash[key]
            self._expired_session_ids.add(session_id)
            self._by_hash.pop(key, None)

    def take_expired_sessions(self) -> set[str]:
        """Return identities removed by expiry so dependent in-memory state can be released."""
        with self._lock:
            return self._take_expired_sessions()

    def sweep_expired(self) -> set[str]:
        """Remove expired sessions and return their ids to dependent state stores."""
        with self._lock:
            self._sweep_expired()
            return self._take_expired_sessions()

    def _take_expired_sessions(self) -> set[str]:
        expired = self._expired_session_ids
        self._expired_session_ids = set()
        return expired

    def live_sessions(self) -> int:
        """给测试和排查用。"""
        with self._lock:
            return len(self._by_hash)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
