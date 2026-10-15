"""Academic audit DTOs: AuditRequest, AuditItem, AuditResult."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import Credits, DomainModel, Id, Issue

AuditState = Literal["SATISFIED", "UNSATISFIED", "UNKNOWN"]


class AuditRequest(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    academicRecordId: Id


class AuditItem(DomainModel):
    requirementId: Id
    courseCodes: list[Id] = Field(max_length=200)
    requiredCredits: Credits | None
    earnedCredits: Credits | None
    gapCredits: Credits | None
    state: AuditState
    sourceRefIds: list[Id] = Field(min_length=1, max_length=20)


class AuditResult(DomainModel):
    curriculumSnapshotId: Id
    academicRecordId: Id
    recordRevision: int
    transcriptComplete: bool
    requirements: list[AuditItem] = Field(max_length=200)
    suggestedCourseCodes: list[Id] = Field(max_length=200)
    unknowns: list[Issue] = Field(max_length=200)
