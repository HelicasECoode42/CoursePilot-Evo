"""In-memory demo session store: only the token hash is kept (docs/04 section 1)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta


class SessionNotFound(Exception):
    """The token is unknown or expired."""


class SessionStore:
    """Local demo store; a real deployment needs a real identity/session design."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._by_hash: dict[str, tuple[str, datetime]] = {}

    def create(self) -> tuple[str, str, datetime]:
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

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
