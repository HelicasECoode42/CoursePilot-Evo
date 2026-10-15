"""Offering DTOs: Meeting, Calendar, CourseOffering, OfferingImport."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from ._base import Credits, DomainModel, Id

ParseStatus = Literal["PARSED", "UNPARSED", "INVALID"]
OfferingSourceKind = Literal["BROWSER_SNAPSHOT", "SYNTHETIC"]

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
    offerings: list[CourseOffering] = Field(min_length=1, max_length=2000)
