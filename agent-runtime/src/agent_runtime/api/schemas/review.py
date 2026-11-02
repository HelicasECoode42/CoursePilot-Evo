"""Review DTOs: ReviewNote, ReviewImport."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import DomainModel, Id

ReviewSourceKind = Literal["OFFICIAL_SYLLABUS", "USER_IMPORT", "EXTERNAL_LINK", "SYNTHETIC"]
ReviewDimension = Literal[
    "GRADING",
    "ATTENDANCE",
    "WORKLOAD",
    "EXAM",
    "GROUP_WORK",
    "PRESENTATION",
    "TEACHING",
    "OVERALL",
]
MatchStatus = Literal["COURSE_TEACHER_MATCHED", "COURSE_ONLY", "UNVERIFIED"]


class ReviewNote(DomainModel):
    reviewNoteId: Id
    courseCode: Id
    teacherKey: Id | None
    termId: Id | None
    sourceKind: ReviewSourceKind
    publishedAt: datetime | None
    sourceUrl: Annotated[str, StringConstraints(max_length=1000)] | None
    excerpt: Annotated[str, StringConstraints(min_length=1, max_length=1500)]
    dimensions: list[ReviewDimension] = Field(max_length=8)
    matchStatus: MatchStatus
    sourceRefId: Id
    teacherDisplayName: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = (
        None
    )


class ReviewImport(DomainModel):
    schemaVersion: Literal["1.0"]
    notes: list[ReviewNote] = Field(min_length=1, max_length=200)
