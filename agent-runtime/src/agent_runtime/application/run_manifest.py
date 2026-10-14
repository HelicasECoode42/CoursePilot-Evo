"""Build a contract-valid RunManifest from the current runtime config."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from agent_runtime.api.schemas import RunManifest
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import new_id


@dataclass(frozen=True)
class RunIdentity:
    """Versions that D later pins. Local planning uses explicit unset markers."""

    java_tool_api_version: str = "java:local-unset"
    verifier_version: str = "verifier:local-unset"
    benchmark_set_version: str = "benchmark:local-unset"
    evaluator_version: str = "evaluator:local-unset"
    parent_version: str | None = None


def build_run_manifest(
    *,
    context: ExecutionContext,
    identity: RunIdentity | None = None,
    run_id: str | None = None,
) -> RunManifest:
    identity = identity or RunIdentity()
    return RunManifest(
        schemaVersion="1.0",
        runId=run_id or new_id("run"),
        benchmarkSetVersion=identity.benchmark_set_version,
        evaluatorVersion=identity.evaluator_version,
        curriculumSnapshotId=context.curriculum_snapshot_id,
        offeringSnapshotId=context.offering_snapshot_id,
        javaToolApiVersion=identity.java_tool_api_version,
        verifierVersion=identity.verifier_version,
        harnessVersion=context.harness_version,
        parentVersion=identity.parent_version,
        modelId=context.model_id,
        temperature=context.temperature,
        maxInputTokens=8000,
        maxOutputTokens=2000,
        maxToolCalls=6,
        maxModelCalls=3,
        deadlineMs=45000,
        repeatCount=1,
        seed=None,
        createdAt=datetime.now(UTC),
    )
