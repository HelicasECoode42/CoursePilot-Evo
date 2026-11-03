"""DTOs for POST /api/v1/offering-summary (per-course section counts, batched)."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ._base import DomainModel, Id


class OfferingSummaryRequest(DomainModel):
    curriculumSnapshotId: Id
    offeringSnapshotId: Id
    courseCodes: list[Id] = Field(min_length=1, max_length=10)


class CourseSectionSummary(DomainModel):
    courseCode: Id
    sectionCount: Annotated[int, Field(ge=0, le=100000)]
    teacherTexts: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(max_length=5)


class OfferingSummaryData(DomainModel):
    curriculumSnapshotId: Id
    offeringSnapshotId: Id
    items: list[CourseSectionSummary] = Field(max_length=10)
    unknownCourseCodes: list[Id] = Field(max_length=10)
