"""Trace DTO: TraceEvent.

Only sanitized fields are recorded; full prompts, reasoning chains, grades and
secrets must never appear here (docs/04-infrastructure-workflow.md section 8).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import DomainModel, Id

EventType = Literal[
    "USER_INPUT",
    "GOAL_EXTRACTED",
    "TOOL_CALLED",
    "TOOL_RETURNED",
    "CANDIDATE_PROPOSED",
    "VERIFIER_RETURNED",
    "CLARIFICATION_REQUESTED",
    "FINAL_DELIVERED",
    "ERROR",
]


class TraceEvent(DomainModel):
    schemaVersion: Literal["1.0"]
    taskId: Id
    traceId: Id
    seq: Annotated[int, Field(ge=1)]
    timestamp: datetime
    eventType: EventType
    harnessVersion: Id
    curriculumSnapshotId: Id
    offeringSnapshotId: Id | None
    toolName: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None
    inputDigest: Annotated[str, StringConstraints(min_length=1, max_length=64)] | None
    outputRef: Id | None
    durationMs: Annotated[int, Field(ge=0)] | None
    inputTokens: Annotated[int, Field(ge=0)] | None
    outputTokens: Annotated[int, Field(ge=0)] | None
    errorCode: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None
