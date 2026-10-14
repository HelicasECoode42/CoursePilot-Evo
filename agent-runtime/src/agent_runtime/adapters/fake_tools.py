"""Typed fake Java tools for W2. Not a real verifier; time stays UNKNOWN."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from agent_runtime.adapters.tool_client import InvalidTool
from agent_runtime.api.schemas import (
    AcademicRecord,
    AuditResult,
    Course,
    Issue,
    PlanValidation,
    TeacherCourseOption,
)
from agent_runtime.application.ids import new_id


class TypedFakeToolClient:
    """Fixed catalog + honest UNKNOWN timetable. Do not treat this as Java."""

    _COURSES = (
        Course(
            courseCode="CS101",
            name="程序设计基础（演示）",
            credits=Decimal("4.00"),
            category="必修",
            sourceRefIds=["source:fake-w2"],
        ),
        Course(
            courseCode="MATH201",
            name="离散数学（演示）",
            credits=Decimal("3.00"),
            category="必修",
            sourceRefIds=["source:fake-w2"],
        ),
    )
    _TEACHERS = (
        TeacherCourseOption(
            courseCode="CS101",
            teacherKey="teacher:demo",
            teacherDisplayName="演示教师",
            availability="UNKNOWN",
            reviewNoteIds=[],
            classIds=[],
        ),
    )

    def call(self, tool: str, dto, context, *, params=None):
        del context, params
        if tool == "auditRequirements":
            return AuditResult(
                curriculumSnapshotId=dto.curriculumSnapshotId,
                academicRecordId=dto.academicRecordId,
                recordRevision=1,
                transcriptComplete=False,
                requirements=[],
                suggestedCourseCodes=["CS101", "MATH201"],
                unknowns=[
                    Issue(
                        code="FAKE_TOOL",
                        message="当前是 W2 类型化假工具，不是 Java 核验",
                        field=None,
                        retryable=False,
                    )
                ],
            )
        if tool == "listCourses":
            return list(self._COURSES)
        if tool == "listTeacherCourseOptions":
            return list(self._TEACHERS)
        if tool == "validatePlan":
            return PlanValidation(
                verifierResultId=new_id("verify"),
                verdict="UNKNOWN",
                scope="COURSE_ONLY",
                curriculumSnapshotId=dto.curriculumSnapshotId,
                offeringSnapshotId=dto.offeringSnapshotId,
                recordRevision=1,
                violations=[],
                unknownChecks=[
                    Issue(
                        code="OFFERING_UNAVAILABLE",
                        message="未取得本学期班次，不能声称无冲突",
                        field="offeringSnapshotId",
                        retryable=False,
                    )
                ],
                performedChecks=["COURSE_EXISTS"],
                sourceRefIds=["source:fake-w2"],
            )
        if tool == "createAcademicRecord":
            return AcademicRecord(
                academicRecordId="record:demo",
                revision=1,
                curriculumSnapshotId=dto.curriculumSnapshotId,
                completedCourses=dto.completedCourses,
                transcriptComplete=dto.transcriptComplete,
                sourceKind=dto.sourceKind,
                createdAt=datetime.now(UTC),
            )
        if tool == "getAcademicRecord":
            return AcademicRecord(
                academicRecordId="record:demo",
                revision=1,
                curriculumSnapshotId="curr:demo",
                completedCourses=[],
                transcriptComplete=False,
                sourceKind="SYNTHETIC",
                createdAt=datetime.now(UTC),
            )
        if tool in {
            "listCurricula",
            "listOfferings",
            "searchReviews",
            "listCareerDirections",
            "listAcademicRecords",
        }:
            return []
        raise InvalidTool(tool)
