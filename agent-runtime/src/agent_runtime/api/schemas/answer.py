"""Planning output DTOs: Question, Recommendation, PlanningAnswer, SessionResult.

``PlanningAnswer`` re-implements the CLARIFY conditional rule: a clarification
answer must carry a Question and must not carry recommendations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from ._base import DomainModel, Id, Issue
from .audit import AuditResult
from .validation import PlanItem, PlanValidation

Decision = Literal["RECOMMENDATIONS", "CLARIFY", "UNABLE_TO_VERIFY"]


class Choice(DomainModel):
    value: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    label: Annotated[str, StringConstraints(min_length=1, max_length=120)]


class Question(DomainModel):
    questionId: Id
    text: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    choices: list[Choice] = Field(max_length=12)
    allowFreeText: bool
    requiredFor: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        max_length=20
    )


class Usage(DomainModel):
    inputTokens: Annotated[int, Field(ge=0)] | None
    outputTokens: Annotated[int, Field(ge=0)] | None
    toolCalls: Annotated[int, Field(ge=0, le=6)]
    elapsedMs: Annotated[int, Field(ge=0)]


class ReviewEvidenceRef(DomainModel):
    reviewNoteId: Id
    sourceRefId: Id


class CourseRationale(DomainModel):
    courseCode: Id
    reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    reviewNoteIds: list[Id] = Field(max_length=10)
    courseSourceRefIds: list[Id] = Field(default_factory=list, max_length=20)
    reviewBasisStatus: Literal["HAS_EVIDENCE", "NO_RECORDS", "NOT_QUERIED"] | None = None
    rationaleSource: Literal["MODEL", "COURSE_FACTS"] | None = None
    reviewEvidenceRefs: list[ReviewEvidenceRef] = Field(default_factory=list, max_length=10)


class ExplorationDirection(DomainModel):
    title: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    description: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    steps: list[Annotated[str, StringConstraints(min_length=1, max_length=300)]] = Field(
        min_length=1, max_length=5
    )


class Recommendation(DomainModel):
    planId: Id
    items: list[PlanItem] = Field(min_length=1, max_length=30)
    explanation: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    reviewNoteIds: list[Id] = Field(max_length=20)
    verification: PlanValidation
    courseRationales: list[CourseRationale] = Field(default_factory=list, max_length=30)
    explorationDirections: list[ExplorationDirection] = Field(default_factory=list, max_length=3)


class PlanningAnswer(DomainModel):
    taskId: Id
    traceId: Id
    decision: Decision
    academicAudit: AuditResult
    recommendations: list[Recommendation] = Field(max_length=3)
    clarification: Question | None
    unknowns: list[Issue] = Field(max_length=200)
    usage: Usage

    @model_validator(mode="after")
    def _clarify_shape(self) -> PlanningAnswer:
        if self.decision == "CLARIFY":
            if self.clarification is None:
                raise ValueError("decision=CLARIFY requires clarification")
            if self.recommendations:
                raise ValueError("decision=CLARIFY requires no recommendations")
        return self


class SessionResult(DomainModel):
    sessionId: Id
    sessionToken: Annotated[str, StringConstraints(min_length=32, max_length=512)]
    expiresAt: datetime
