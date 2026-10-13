"""The trusted context handed to the Runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExecutionContext:
    """Separates identity, deadline, model config and snapshots (c-agent.md section 2).

    ``subject_id`` is the server-resolved principal, never the browser-supplied id.
    """

    subject_id: str
    request_id: str
    curriculum_snapshot_id: str
    offering_snapshot_id: str | None
    model_id: str
    temperature: float
    deadline: datetime
    harness_version: str
