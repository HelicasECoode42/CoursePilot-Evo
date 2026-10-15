"""Collects sanitized TraceEvents for one run."""

from __future__ import annotations

from datetime import UTC, datetime

from agent_runtime.api.schemas import TraceEvent


class TracePort:
    """seq increments within the trace; only allowed fields are recorded.

    Full prompts, private reasoning chains, grades, identity and secrets are
    intentionally absent from TraceEvent (docs/04 section 8).
    """

    def __init__(
        self,
        *,
        task_id: str,
        trace_id: str,
        harness_version: str,
        curriculum_snapshot_id: str,
        offering_snapshot_id: str | None,
    ) -> None:
        self._task_id = task_id
        self._trace_id = trace_id
        self._harness_version = harness_version
        self._curriculum = curriculum_snapshot_id
        self._offering = offering_snapshot_id
        self._seq = 0
        self._events: list[TraceEvent] = []

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def emit(
        self,
        event_type: str,
        *,
        tool_name: str | None = None,
        input_digest: str | None = None,
        output_ref: str | None = None,
        duration_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error_code: str | None = None,
    ) -> TraceEvent:
        self._seq += 1
        event = TraceEvent(
            schemaVersion="1.0",
            taskId=self._task_id,
            traceId=self._trace_id,
            seq=self._seq,
            timestamp=datetime.now(UTC),
            eventType=event_type,
            harnessVersion=self._harness_version,
            curriculumSnapshotId=self._curriculum,
            offeringSnapshotId=self._offering,
            toolName=tool_name,
            inputDigest=input_digest,
            outputRef=output_ref,
            durationMs=duration_ms,
            inputTokens=input_tokens,
            outputTokens=output_tokens,
            errorCode=error_code,
        )
        self._events.append(event)
        return event
