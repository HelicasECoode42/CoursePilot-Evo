"""Run/benchmark DTOs: RunManifest and auxiliary report/import models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import DomainModel, Id, Issue
from .goal import SoftPreference

RunDecision = Literal["BASELINE", "PROMOTED", "REJECTED"]
ImportState = Literal["PUBLISHED", "REJECTED"]


class RunManifest(DomainModel):
    schemaVersion: Literal["1.0"]
    runId: Id
    benchmarkSetVersion: Id
    evaluatorVersion: Id
    curriculumSnapshotId: Id
    offeringSnapshotId: Id | None
    javaToolApiVersion: Id
    verifierVersion: Id
    harnessVersion: Id
    parentVersion: Id | None
    modelId: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    temperature: Annotated[float, Field(ge=0, le=2)]
    maxInputTokens: Literal[8000]
    maxOutputTokens: Literal[4000]
    maxToolCalls: Literal[6]
    maxModelCalls: Literal[3]
    deadlineMs: Literal[45000]
    repeatCount: Annotated[int, Field(ge=1, le=10)]
    seed: int | None
    createdAt: datetime


class PreferenceMetric(DomainModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    value: float
    unit: Annotated[str, StringConstraints(min_length=1, max_length=80)]


class PreferenceScoreRequest(DomainModel):
    schemaVersion: Literal["1.0"]
    verifierResultId: Id
    preferences: list[SoftPreference] = Field(max_length=30)


class PreferenceScore(DomainModel):
    verifierResultId: Id
    metrics: list[PreferenceMetric] = Field(max_length=30)
    unknownMetrics: list[Issue] = Field(max_length=200)


class ImportResult(DomainModel):
    snapshotId: Id | None
    state: ImportState
    reused: bool
    issues: list[Issue] = Field(max_length=200)


class ImportWorkbook(DomainModel):
    schemaVersion: Literal["1.0"]
    trackId: Id
    file: str


class RunReport(DomainModel):
    runId: str
    harnessVersion: str
    parentVersion: str | None
    decision: RunDecision
    heldOutScore: float | None
    averageInputTokens: float | None
    averageOutputTokens: float | None
    averageToolCalls: float | None
    averageLatencyMs: float | None
    failureCategories: list[str] = Field(max_length=30)
