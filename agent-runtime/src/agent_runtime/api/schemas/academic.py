"""Academic-record DTOs: CompletedCourse, AcademicRecordInput, AcademicRecord."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ._base import Credits, DomainModel, Id

Outcome = Literal["PASSED", "FAILED", "IN_PROGRESS", "UNKNOWN"]
RecordSourceKind = Literal["USER_IMPORT", "SYNTHETIC"]


class CompletedCourse(DomainModel):
    courseCode: Id
    earnedCredits: Credits | None
    outcome: Outcome
    completedTerm: Id | None


class AcademicRecordInput(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    completedCourses: list[CompletedCourse] = Field(max_length=500)
    transcriptComplete: bool
    sourceKind: RecordSourceKind


class AcademicRecord(DomainModel):
    academicRecordId: Id
    revision: int
    curriculumSnapshotId: Id
    completedCourses: list[CompletedCourse] = Field(max_length=500)
    transcriptComplete: bool
    sourceKind: RecordSourceKind
    createdAt: datetime
