"""Idempotency store: reuse completed answers; in-flight same key is 409."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock


class IdempotencyConflict(Exception):
    """Same Idempotency-Key but a different request body (-> 409)."""

    def __str__(self) -> str:
        return "Idempotency-Key 已用于不同内容的请求"


class RequestInProgress(Exception):
    """Same key is currently executing; do not start a second run (-> 409)."""

    def __str__(self) -> str:
        return "相同幂等键的请求正在执行"


@dataclass
class _Entry:
    digest: str
    payload: dict | None
    in_progress: bool
    failure: Exception | None = None


class IdempotencyStore:
    """Key = (session, endpoint, key), matching docs/04 section 3.

    Endpoints may cache selected terminal failures; the default keeps failures
    retryable so existing routes retain their prior behavior.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[tuple[str, str, str], _Entry] = {}

    def begin(self, session_id: str, endpoint: str, key: str, body_digest: str) -> dict | None:
        slot = (session_id, endpoint, key)
        with self._lock:
            entry = self._entries.get(slot)
            if entry is None:
                self._entries[slot] = _Entry(digest=body_digest, payload=None, in_progress=True)
                return None
            if entry.digest != body_digest:
                raise IdempotencyConflict
            if entry.in_progress:
                raise RequestInProgress
            if entry.failure is not None:
                raise entry.failure
            return entry.payload

    def complete(
        self, session_id: str, endpoint: str, key: str, body_digest: str, answer: dict
    ) -> None:
        slot = (session_id, endpoint, key)
        with self._lock:
            self._entries[slot] = _Entry(digest=body_digest, payload=answer, in_progress=False)

    def abort(self, session_id: str, endpoint: str, key: str) -> None:
        slot = (session_id, endpoint, key)
        with self._lock:
            entry = self._entries.get(slot)
            if entry is not None and entry.in_progress:
                del self._entries[slot]

    def complete_failure(
        self,
        session_id: str,
        endpoint: str,
        key: str,
        body_digest: str,
        failure: Exception,
    ) -> None:
        """Cache a selected terminal failure without changing other endpoint defaults."""
        slot = (session_id, endpoint, key)
        with self._lock:
            self._entries[slot] = _Entry(
                digest=body_digest, payload=None, in_progress=False, failure=failure
            )

    def run(
        self,
        session_id: str,
        endpoint: str,
        key: str,
        body_digest: str,
        produce: Callable[[], dict],
        *,
        cache_failure: Callable[[Exception], bool] | None = None,
    ) -> dict:
        cached = self.begin(session_id, endpoint, key, body_digest)
        if cached is not None:
            return cached
        try:
            payload = produce()
        except Exception as exc:
            if cache_failure is not None and cache_failure(exc):
                self.complete_failure(session_id, endpoint, key, body_digest, exc)
            else:
                self.abort(session_id, endpoint, key)
            raise
        self.complete(session_id, endpoint, key, body_digest, payload)
        return payload
