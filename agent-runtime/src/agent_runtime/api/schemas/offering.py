"""Offering DTOs: Meeting, Calendar, CourseOffering, OfferingImport, verification."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from ._base import Credits, DomainModel, Id

ParseStatus = Literal["PARSED", "UNPARSED", "INVALID"]
OfferingSourceKind = Literal["BROWSER_SNAPSHOT", "OFFICIAL_DOCUMENT", "SYNTHETIC"]

Week = Annotated[int, Field(ge=1, le=60)]


class Meeting(DomainModel):
    dayOfWeek: Annotated[int, Field(ge=1, le=7)]
    sectionStart: Annotated[int, Field(ge=1, le=64)]
    sectionEnd: Annotated[int, Field(ge=1, le=64)]
    weeks: list[Week] = Field(min_length=1, max_length=60)

    @field_validator("weeks")
    @classmethod
    def _unique_weeks(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("weeks must be unique")
        return value


class Calendar(DomainModel):
    weeks: Annotated[int, Field(ge=1, le=60)]
    sectionsPerDay: Annotated[int, Field(ge=1, le=64)]


class CourseOffering(DomainModel):
    courseCode: Id
    classId: Id
    teacherKey: Id | None
    teacherText: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    credits: Credits | None
    capacity: Annotated[int, Field(ge=0, le=100000)] | None
    meetingTextRaw: Annotated[str, StringConstraints(max_length=1000)]
    meetings: list[Meeting] = Field(max_length=40)
    parseStatus: ParseStatus
    sourceRefId: Id


class OfferingImport(DomainModel):
    schemaVersion: Literal["1.0"]
    termId: Id
    sourceKind: OfferingSourceKind
    capturedAt: datetime
    calendar: Calendar
    # 7000 matches contracts/schemas/domain.schema.json: a whole official term (6431
    # rows for 2026-27 autumn) must fit in one snapshot.
    offerings: list[CourseOffering] = Field(min_length=1, max_length=7000)


Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class OfferingVerificationRequest(DomainModel):
    """Sampling report submitted by a verifier for an offering snapshot (admin route)."""

    schemaVersion: Literal["1.0"]
    verifierName: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    uploaderName: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    sampleSize: Annotated[int, Field(ge=30, le=100000)]
    errorCount: Annotated[int, Field(ge=0, le=100000)]
    sampleFileSha256: Sha256Hex
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class OfferingVerificationResult(DomainModel):
    snapshotId: Id
    verificationId: Id
    outcome: Literal["VERIFIED", "REJECTED"]
    sourceValidation: Literal["VERIFIED", "UNVERIFIED"]
    sampleSize: Annotated[int, Field(ge=30, le=100000)]
    errorCount: Annotated[int, Field(ge=0, le=100000)]
    verifiedAt: datetime
