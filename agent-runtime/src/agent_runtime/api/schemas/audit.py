"""Academic audit DTOs: AuditRequest, AuditItem, AuditResult."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import Credits, DomainModel, Id, Issue

AuditState = Literal["SATISFIED", "UNSATISFIED", "UNKNOWN"]


class AuditRequest(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    academicRecordId: Id


class AuditItem(DomainModel):
    requirementId: Id
    # 类别名（必修 / 通识 …）。没有它前端只能显示「培养要求 1」。
    category: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None
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
