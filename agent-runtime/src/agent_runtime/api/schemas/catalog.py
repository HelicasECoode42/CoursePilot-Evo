"""Catalog DTOs: Course, SnapshotSummary, TeacherCourseOption, CareerDirection."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import Credits, DomainModel, Id

SnapshotKind = Literal["CURRICULUM", "OFFERING"]
SnapshotState = Literal["PUBLISHED", "REJECTED"]
SnapshotSourceKind = Literal[
    "CURRICULUM_FILE", "BROWSER_SNAPSHOT", "OFFICIAL_DOCUMENT", "SYNTHETIC"
]
SourceValidation = Literal["VERIFIED", "UNVERIFIED", "SYNTHETIC"]
Availability = Literal["CURRENT_VERIFIED", "HISTORICAL_ONLY", "UNKNOWN"]


class Course(DomainModel):
    courseCode: Id
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    credits: Credits | None
    category: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    sourceRefIds: list[Id] = Field(min_length=1, max_length=20)
    suggestedTerm: Annotated[str, StringConstraints(max_length=200)] | None = None


class SnapshotSummary(DomainModel):
    snapshotId: Id
    kind: SnapshotKind
    state: SnapshotState
    sourceKind: SnapshotSourceKind
    termId: Id | None
    createdAt: datetime
    sourceValidation: SourceValidation
    displayName: Annotated[str, StringConstraints(max_length=200)] | None = None


OfferingFactSource = Literal["TEACHER_BINDING", "OFFERING_SNAPSHOT"]


class TeacherCourseOption(DomainModel):
    courseCode: Id
    teacherKey: Id
    teacherDisplayName: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    availability: Availability
    reviewNoteIds: list[Id] = Field(max_length=200)
    classIds: list[Id] = Field(max_length=200)
    # 以下五项为可选新增（contracts/README.md 变更记录）；旧数据缺省为 None。
    courseName: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None
    sectionCount: Annotated[int, Field(ge=0)] | None = None
    offeringSnapshotId: Id | None = None
    offeringSourceValidation: SourceValidation | None = None
    factSource: OfferingFactSource | None = None


class CareerDirection(DomainModel):
    directionId: Id
    subjectTags: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        min_length=1, max_length=20
    )
    title: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    description: Annotated[str, StringConstraints(min_length=1, max_length=1500)]
    courseCodes: list[Id] = Field(max_length=100)
    sourceRefIds: list[Id] = Field(min_length=1, max_length=20)
