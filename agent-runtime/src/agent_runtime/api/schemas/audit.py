"""Academic audit DTOs: AuditRequest, AuditItem, AuditResult."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from ._base import Credits, DomainModel, Id, Issue

AuditState = Literal["SATISFIED", "UNSATISFIED", "UNKNOWN"]
# LOCAL：本地课程折算；SCHOOL_REPORT：学分取自学校报告的同名类别。缺省视为 LOCAL。
AuditSource = Literal["LOCAL", "SCHOOL_REPORT"]
# transcriptComplete 为 true 时的依据；为 false 时为 None。
TranscriptCompleteSource = Literal["SCHOOL_IMPORT_FULL", "MANUAL"]


class AuditRequest(DomainModel):
    schemaVersion: Literal["1.0"]
    curriculumSnapshotId: Id
    academicRecordId: Id


class AuditItem(DomainModel):
    requirementId: Id
    # 类别名（必修 / 通识 …）。没有它前端只能显示「培养要求 1」。
    category: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None
    courseCodes: list[Id] = Field(max_length=500)
    requiredCredits: Credits | None
    earnedCredits: Credits | None
    gapCredits: Credits | None
    state: AuditState
    sourceRefIds: list[Id] = Field(min_length=1, max_length=20)
    # 可选字段：旧数据与旧提供者缺省时为 None，不影响既有构造。
    source: AuditSource | None = None
    # 在读课程学分，不计入 earnedCredits；学分未知时为 None。
    inProgressCredits: Credits | None = None


class AuditResult(DomainModel):
    curriculumSnapshotId: Id
    academicRecordId: Id
    recordRevision: int
    transcriptComplete: bool
    transcriptCompleteSource: TranscriptCompleteSource | None = None
    requirements: list[AuditItem] = Field(max_length=200)
    suggestedCourseCodes: list[Id] = Field(max_length=200)
    # One issue per recorded course, plus three audit-level notices.
    unknowns: list[Issue] = Field(max_length=503)
