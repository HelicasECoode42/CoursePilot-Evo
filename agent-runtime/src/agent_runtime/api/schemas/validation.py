"""Plan validation DTOs: PlanItem, PlanValidationRequest, PlanValidation.

``PlanValidation`` re-implements the schema's conditional ``allOf`` rules as
model validators so that ``invalid-valid-with-unknown.json`` is rejected.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from ._base import DomainModel, Id, Issue
from .goal import Constraint

Verdict = Literal["VALID", "INVALID", "UNKNOWN"]
Scope = Literal["COURSE_ONLY", "REAL_TIMETABLE", "SIMULATION"]
ValidationMode = Literal["REAL", "SIMULATION"]


class PlanItem(DomainModel):
    courseCode: Id
    teacherKey: Id | None
    classId: Id | None


class PlanValidationRequest(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    offeringSnapshotId: Id | None
    academicRecordId: Id
    mode: ValidationMode
    items: list[PlanItem] = Field(min_length=1, max_length=30)
    hardConstraints: list[Constraint] = Field(max_length=30)


class PlanValidation(DomainModel):
    verifierResultId: Id
    verdict: Verdict
    scope: Scope
    curriculumSnapshotId: Id
    offeringSnapshotId: Id | None
    recordRevision: int
    violations: list[Issue] = Field(max_length=200)
    unknownChecks: list[Issue] = Field(max_length=200)
    performedChecks: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        max_length=40
    )
    sourceRefIds: list[Id] = Field(max_length=200)

    @model_validator(mode="after")
    def _valid_implies_no_open_checks(self) -> PlanValidation:
        if self.verdict == "VALID" and (self.violations or self.unknownChecks):
            raise ValueError("verdict=VALID requires empty violations and unknownChecks")
        return self

    @model_validator(mode="after")
    def _time_scope_requires_offering(self) -> PlanValidation:
        if self.scope in ("REAL_TIMETABLE", "SIMULATION") and self.offeringSnapshotId is None:
            raise ValueError("scope REAL_TIMETABLE/SIMULATION requires offeringSnapshotId")
        return self


class SessionPlanCourseRemovalRequest(DomainModel):
    previousPlanId: Id
    courseCode: Id


class SessionPlanEditResult(DomainModel):
    previousPlanId: Id
    planId: Id
    items: list[PlanItem] = Field(max_length=30)
    hardConstraints: list[Constraint] = Field(max_length=30)
    verification: PlanValidation | None
    empty: bool

    @model_validator(mode="after")
    def _empty_plan_has_no_verification(self) -> SessionPlanEditResult:
        if self.empty != (len(self.items) == 0):
            raise ValueError("empty must match whether items is empty")
        if self.empty and self.verification is not None:
            raise ValueError("empty plan cannot carry a verification")
        if not self.empty and self.verification is None:
            raise ValueError("non-empty plan requires a verification")
        return self
