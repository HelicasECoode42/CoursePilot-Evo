"""Minimal idempotency store: same key + same content reuses; different content 409."""

from __future__ import annotations


class IdempotencyConflict(Exception):
    """Same Idempotency-Key but a different request body (-> 409)."""


class IdempotencyStore:
    """Key = (session, endpoint, key), matching docs/04 section 3. In-memory skeleton."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], tuple[str, dict]] = {}

    def resolve(self, session_id: str, endpoint: str, key: str, body_digest: str) -> dict | None:
        entry = self._entries.get((session_id, endpoint, key))
        if entry is None:
            return None
        existing_digest, cached = entry
        if existing_digest != body_digest:
            raise IdempotencyConflict
        return cached

    def store(
        self, session_id: str, endpoint: str, key: str, body_digest: str, answer: dict
    ) -> None:
        self._entries[(session_id, endpoint, key)] = (body_digest, answer)
