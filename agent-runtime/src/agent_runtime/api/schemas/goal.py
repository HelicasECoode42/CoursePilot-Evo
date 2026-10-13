"""Goal and planning-request DTOs: Constraint, TeacherPreference, GoalIntent, PlanningRequest."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import Credits, DomainModel, Id

Motive = Literal[
    "GPA",
    "LOW_WORKLOAD",
    "LOW_ATTENDANCE",
    "GOOD_REVIEWS",
    "SPECIFIC_TEACHER",
    "INTEREST",
    "CAREER",
    "POSTGRAD",
    "CREDIT_PROGRESS",
    "SCHEDULE",
]

ConstraintKind = Literal[
    "BLOCK_DAY",
    "BLOCK_SECTION",
    "PIN_TEACHER_COURSE",
    "PIN_COURSE",
    "MAX_CREDITS",
]

TeacherPreferenceMode = Literal["MUST", "PREFER"]

PlanningMode = Literal["REAL", "SIMULATION"]


class Constraint(DomainModel):
    kind: ConstraintKind
    courseCode: Id | None
    teacherKey: Id | None
    dayOfWeek: Annotated[int, Field(ge=1, le=7)] | None
    section: Annotated[int, Field(ge=1, le=64)] | None
    value: Credits | None
    sourceText: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class TeacherPreference(DomainModel):
    courseCode: Id
    teacherKey: Id
    mode: TeacherPreferenceMode


class SoftPreference(DomainModel):
    """One soft preference; also reused by PreferenceScoreRequest.preferences."""

    dimension: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    value: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    sourceText: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class GoalIntent(DomainModel):
    motives: list[Motive] = Field(max_length=10)
    priorityOrder: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        max_length=10
    )
    hardConstraints: list[Constraint] = Field(max_length=30)
    softPreferences: list[SoftPreference] = Field(max_length=30)
    pinnedTeacherCoursePairs: list[TeacherPreference] = Field(max_length=20)
    interestTags: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        max_length=20
    )
    careerDirectionIds: list[Id] = Field(max_length=10)


class PlanningRequest(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    offeringSnapshotId: Id | None
    academicRecordId: Id
    mode: PlanningMode
    promptText: Annotated[str, StringConstraints(max_length=4000)]
    intent: GoalIntent
    previousPlanId: Id | None
