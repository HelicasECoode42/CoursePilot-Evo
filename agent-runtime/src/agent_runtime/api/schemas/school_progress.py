"""School progress snapshot accepted from the user's installed browser adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import Credits, DomainModel, Id
from .academic import AcademicRecord


class SchoolProgressNode(DomainModel):
    nodeId: Id
    parentId: Id | None
    schoolNodeId: str | None = Field(max_length=120)
    leaf: bool
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    requiredCredits: Credits | None
    earnedCredits: Credits | None
    remainingCredits: Credits | None


class SchoolProgressCourse(DomainModel):
    nodeId: Id
    courseCode: Id
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    credits: Credits | None
    outcome: Literal["PASSED", "FAILED", "IN_PROGRESS", "NOT_TAKEN", "UNKNOWN"]
    completedYear: str | None = Field(max_length=80)
    completedTerm: str | None = Field(max_length=80)
    grade: str | None = Field(max_length=80)
    makeup: str | None = Field(max_length=80)
    retake: str | None = Field(max_length=80)
    suggestedYear: str | None = Field(max_length=80)
    suggestedTerm: str | None = Field(max_length=80)


class SchoolProgressSnapshot(DomainModel):
    format: Literal["coursepilot-shu-academic-progress"]
    version: Literal[1]
    capturedAt: datetime
    source: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    nodes: list[SchoolProgressNode] = Field(min_length=1, max_length=1000)
    courses: list[SchoolProgressCourse] = Field(max_length=1000)


class SchoolProgressImport(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    snapshot: SchoolProgressSnapshot


class SchoolProgressReceipt(DomainModel):
    schoolProgressId: Id
    contentHash: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    importedAt: datetime
    reused: bool


class SchoolProgressImportResult(DomainModel):
    receipt: SchoolProgressReceipt
    snapshot: SchoolProgressSnapshot
    academicRecord: AcademicRecord
