"""Wire DTOs for one-turn advice chat."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import Credits, DomainModel, Id, Issue
from .answer import Usage
from .goal import PlanningMode
from .review import ReviewNote


class AdviceChatMessage(DomainModel):
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=3000)]


class AdviceChatRequest(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    academicRecordId: Id | None
    mode: PlanningMode
    message: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    history: list[AdviceChatMessage] = Field(max_length=8)
    interestText: Annotated[str, StringConstraints(max_length=1000)]
    selectedCourseCodes: list[Id] = Field(max_length=10)
    preferredCourseCodes: list[Id] = Field(default_factory=list, max_length=10)


class AdviceChatCourse(DomainModel):
    courseCode: Id
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    credits: Credits | None
    category: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    reviewNoteIds: list[Id] = Field(max_length=10)
    reviews: list[ReviewNote] = Field(max_length=10)
    reviewStatus: Literal["AVAILABLE", "NONE", "NOT_QUERIED", "UNKNOWN"]


class AdviceChatSuggestion(DomainModel):
    suggestionId: Id
    kind: Literal["INTEREST", "SELECT_COURSE", "PREFER_COURSE"]
    label: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    value: Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class AdviceSchoolProgressNode(DomainModel):
    nodeId: Id
    parentId: Id | None
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    requiredCredits: Credits | None
    earnedCredits: Credits | None
    remainingCredits: Credits | None


class AdviceSchoolProgress(DomainModel):
    capturedAt: str
    source: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    nodes: list[AdviceSchoolProgressNode] = Field(max_length=1000)


class AdviceChatAnswer(DomainModel):
    schemaVersion: Literal["1.0"]
    reply: Annotated[str, StringConstraints(min_length=1, max_length=3000)]
    question: Annotated[str, StringConstraints(min_length=1, max_length=1000)] | None
    courses: list[AdviceChatCourse] = Field(max_length=5)
    suggestions: list[AdviceChatSuggestion] = Field(max_length=6)
    schoolProgress: AdviceSchoolProgress | None
    unknowns: list[Issue] = Field(max_length=200)
    usage: Usage
