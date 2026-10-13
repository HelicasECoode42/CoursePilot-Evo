"""Small id/digest helpers used across the runner and the API layer."""

from __future__ import annotations

import hashlib
import uuid


def new_id(prefix: str) -> str:
    """A contract-valid id like ``task:<hex>`` (matches the ``Id`` pattern)."""
    return f"{prefix}:{uuid.uuid4().hex}"


def digest(text: str) -> str:
    """SHA-256 hex digest (64 chars), used for sanitized Trace inputDigest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
