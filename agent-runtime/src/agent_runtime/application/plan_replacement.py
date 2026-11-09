"""Search offerings and replace one course inside a session-owned plan.

Java remains the verifier. This module calls the existing ``listOfferings`` and
``validatePlan`` tools, keeps every other course and the original hard
constraints, and returns the new validation unchanged. It does not invent a
``VALID`` verdict when Java is down or when the offering snapshot is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from agent_runtime.api.schemas import (
    AcademicRecord,
    Constraint,
    Course,
    CourseOffering,
    PlanItem,
    PlanValidation,
    PlanValidationRequest,
)
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import new_id
from agent_runtime.application.offering_check import COURSE_OFFERING_LIMIT
from agent_runtime.application.plan_store import PlanNotInSession, SavedPlan, SessionPlanStore


class CourseNotInPlan(Exception):
    """The saved plan does not contain exactly one item for the target course."""


class UnknownClass(Exception):
    """The selected class is not in this course's current offering query."""


class OfferingSnapshotMissing(Exception):
    """The saved plan has no offering snapshot, so a class search cannot run."""


class ReusedVerification(Exception):
    """Java returned the previous verifier result id. That verdict is not new."""


MAX_PLAN_ITEMS = 30  # planning.openapi.json: items maxItems 30


class CourseNotFound(Exception):
    """The course is in neither the plan's curriculum nor its offering snapshot."""


class CourseAlreadyInPlan(Exception):
    """The saved plan already holds this course."""


class CourseAlreadyTaken(Exception):
    """The academic record shows this course as PASSED or IN_PROGRESS."""


class PlanFull(Exception):
    """The plan already holds MAX_PLAN_ITEMS courses."""


class ClassNeedsSnapshot(Exception):
    """A class was named for a plan that has no offering snapshot to check it against."""


class ToolCaller(Protocol):
    def call(
        self,
        tool: str,
        dto: Any,
        context: ExecutionContext,
        *,
        params: dict[str, object] | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class ReplacementResult:
    previous_plan_id: str
    plan_id: str
    items: list[PlanItem]
    hard_constraints: list[Constraint]
    verification: PlanValidation | None
    empty: bool = False


@dataclass(frozen=True)
class MustAvoidCheck:
    """Java's verdict on one candidate class against the hard time constraints."""

    classId: str
    verdict: str  # CONFLICT | CLEAR_UNVERIFIED | CLEAR | UNKNOWN


# Java's preview codes for a source that is not verified (see PlanValidationService).
_HIT_UNVERIFIED = "CONSTRAINT_HIT_UNVERIFIED_SOURCE"
_CLEAR_UNVERIFIED = "CONSTRAINT_CLEAR_UNVERIFIED_SOURCE"


def _must_avoid_verdict(verification: PlanValidation) -> str:
    """Map Java's constraint findings for one candidate to a preview verdict.

    Java decides; this only names the result. A hit is a CONFLICT even when the
    source is unverified, because the parsed meeting time really falls inside a
    must-avoid slot. A miss on unverified data is CLEAR_UNVERIFIED, not CLEAR.
    Anything Java could not decide is UNKNOWN.
    """
    if any(item.code.startswith("CONSTRAINT_BLOCK_") for item in verification.violations):
        return "CONFLICT"
    unknown_codes = [item.code for item in verification.unknownChecks]
    if any(code == _HIT_UNVERIFIED for code in unknown_codes):
        return "CONFLICT"
    if any(code.startswith("CONSTRAINT_") and code != _CLEAR_UNVERIFIED for code in unknown_codes):
        return "UNKNOWN"
    if any(code == _CLEAR_UNVERIFIED for code in unknown_codes):
        return "CLEAR_UNVERIFIED"
    return "CLEAR"


class PlanReplacement:
    def __init__(self, plans: SessionPlanStore, tools: ToolCaller) -> None:
        self._plans = plans
        self._tools = tools

    def search(
        self,
        *,
        session_id: str,
        previous_plan_id: str,
        course_code: str,
        context: ExecutionContext,
    ) -> list[CourseOffering]:
        plan = self._require_plan(session_id, previous_plan_id)
        return self._load_offerings(plan, course_code, context)

    def check_must_avoid(
        self,
        *,
        session_id: str,
        previous_plan_id: str,
        offerings: list[CourseOffering],
        context: ExecutionContext,
    ) -> list[MustAvoidCheck]:
        """Ask Java whether each candidate class breaks a hard time constraint.

        Each candidate is validated alone against the saved hard time constraints.
        Java does the time math. This only maps its CONSTRAINT_BLOCK_* findings
        to CONFLICT / UNKNOWN / CLEAR. A plan without hard time constraints needs no
        Java call and gets no checks.
        """
        plan = self._require_plan(session_id, previous_plan_id)
        constraints = [
            item.model_copy(deep=True)
            for item in plan.hard_constraints
            if item.kind in ("BLOCK_DAY", "BLOCK_SECTION", "BLOCK_SLOT")
        ]
        if not constraints or plan.offering_snapshot_id is None:
            return []
        checks: list[MustAvoidCheck] = []
        for offering in offerings:
            candidate = PlanItem(
                courseCode=offering.courseCode,
                teacherKey=offering.teacherKey,
                classId=offering.classId,
            )
            verification = cast(
                PlanValidation,
                self._tools.call(
                    "validatePlan",
                    PlanValidationRequest(
                        schemaVersion="1.0",
                        curriculumSnapshotId=plan.curriculum_snapshot_id,
                        offeringSnapshotId=plan.offering_snapshot_id,
                        academicRecordId=plan.academic_record_id,
                        mode=plan.mode,
                        items=[candidate],
                        hardConstraints=constraints,
                    ),
                    context,
                ),
            )
            checks.append(
                MustAvoidCheck(
                    classId=offering.classId,
                    verdict=_must_avoid_verdict(verification),
                )
            )
        return checks

    def replace(
        self,
        *,
        session_id: str,
        previous_plan_id: str,
        course_code: str,
        selected_class_id: str,
        context: ExecutionContext,
    ) -> ReplacementResult:
        plan = self._require_plan(session_id, previous_plan_id)
        _ensure_single_course(plan, course_code)
        selected = self._selected_offering(plan, course_code, selected_class_id, context)
        items = _replaced_items(plan, course_code, selected)
        constraints = [item.model_copy(deep=True) for item in plan.hard_constraints]
        verification = cast(
            PlanValidation,
            self._tools.call(
                "validatePlan",
                PlanValidationRequest(
                    schemaVersion="1.0",
                    curriculumSnapshotId=plan.curriculum_snapshot_id,
                    offeringSnapshotId=plan.offering_snapshot_id,
                    academicRecordId=plan.academic_record_id,
                    mode=plan.mode,
                    items=items,
                    hardConstraints=constraints,
                ),
                context,
            ),
        )
        if verification.verifierResultId == plan.verifier_result_id:
            raise ReusedVerification
        plan_id = new_id("plan")
        self._plans.remember(
            session_id=session_id,
            plan_id=plan_id,
            curriculum_snapshot_id=plan.curriculum_snapshot_id,
            offering_snapshot_id=plan.offering_snapshot_id,
            academic_record_id=plan.academic_record_id,
            mode=plan.mode,
            items=items,
            hard_constraints=constraints,
            verifier_result_id=verification.verifierResultId,
        )
        return ReplacementResult(
            previous_plan_id=plan.plan_id,
            plan_id=plan_id,
            items=items,
            hard_constraints=constraints,
            verification=verification,
        )

    def add_course(
        self,
        *,
        session_id: str,
        previous_plan_id: str,
        course_code: str,
        class_id: str | None,
        context: ExecutionContext,
    ) -> ReplacementResult:
        """Add one course deterministically, then revalidate the whole new plan.

        Checks run before any Java validatePlan call: course not already in the plan,
        not PASSED or IN_PROGRESS on the record, present in the curriculum or the
        offering snapshot, and a named class belongs to this course in that snapshot.
        """
        plan = self._require_plan(session_id, previous_plan_id)
        if any(item.courseCode == course_code for item in plan.items):
            raise CourseAlreadyInPlan
        if len(plan.items) >= MAX_PLAN_ITEMS:
            raise PlanFull
        self._ensure_not_taken(plan, course_code, context)

        offerings: list[CourseOffering] = []
        if plan.offering_snapshot_id is not None:
            offerings = self._load_offerings(plan, course_code, context)
        elif class_id is not None:
            raise ClassNeedsSnapshot
        if not offerings and not self._in_curriculum(plan, course_code, context):
            raise CourseNotFound

        teacher_key: str | None = None
        if class_id is not None:
            selected = next((item for item in offerings if item.classId == class_id), None)
            if selected is None:
                raise UnknownClass
            teacher_key = selected.teacherKey

        items = [item.model_copy(deep=True) for item in plan.items]
        items.append(PlanItem(courseCode=course_code, teacherKey=teacher_key, classId=class_id))
        constraints = [item.model_copy(deep=True) for item in plan.hard_constraints]
        verification = cast(
            PlanValidation,
            self._tools.call(
                "validatePlan",
                PlanValidationRequest(
                    schemaVersion="1.0",
                    curriculumSnapshotId=plan.curriculum_snapshot_id,
                    offeringSnapshotId=plan.offering_snapshot_id,
                    academicRecordId=plan.academic_record_id,
                    mode=plan.mode,
                    items=items,
                    hardConstraints=constraints,
                ),
                context,
            ),
        )
        if verification.verifierResultId == plan.verifier_result_id:
            raise ReusedVerification
        plan_id = new_id("plan")
        self._plans.remember(
            session_id=session_id,
            plan_id=plan_id,
            curriculum_snapshot_id=plan.curriculum_snapshot_id,
            offering_snapshot_id=plan.offering_snapshot_id,
            academic_record_id=plan.academic_record_id,
            mode=plan.mode,
            items=items,
            hard_constraints=constraints,
            verifier_result_id=verification.verifierResultId,
        )
        return ReplacementResult(
            previous_plan_id=plan.plan_id,
            plan_id=plan_id,
            items=items,
            hard_constraints=constraints,
            verification=verification,
        )

    def _ensure_not_taken(
        self, plan: SavedPlan, course_code: str, context: ExecutionContext
    ) -> None:
        record = cast(
            AcademicRecord,
            self._tools.call(
                "getAcademicRecord",
                None,
                context,
                params={"recordId": plan.academic_record_id},
            ),
        )
        for completed in record.completedCourses:
            if completed.courseCode == course_code and completed.outcome in (
                "PASSED",
                "IN_PROGRESS",
            ):
                raise CourseAlreadyTaken

    def _in_curriculum(self, plan: SavedPlan, course_code: str, context: ExecutionContext) -> bool:
        courses = cast(
            list[Course],
            self._tools.call(
                "listCourses",
                None,
                context,
                params={
                    "curriculumSnapshotId": plan.curriculum_snapshot_id,
                    "query": course_code,
                    "limit": 200,
                },
            ),
        )
        return any(course.courseCode == course_code for course in courses)

    def remove(
        self,
        *,
        session_id: str,
        previous_plan_id: str,
        course_code: str,
        context: ExecutionContext,
    ) -> ReplacementResult:
        """Remove one course deterministically and revalidate the remaining plan."""
        plan = self._require_plan(session_id, previous_plan_id)
        _ensure_single_course(plan, course_code)
        items = [
            item.model_copy(deep=True) for item in plan.items if item.courseCode != course_code
        ]
        constraints = [
            item.model_copy(deep=True)
            for item in plan.hard_constraints
            if not (
                (item.kind == "PIN_COURSE" and item.courseCode == course_code)
                or (item.kind == "PIN_TEACHER_COURSE" and item.courseCode == course_code)
            )
        ]
        verification = None
        if items:
            verification = cast(
                PlanValidation,
                self._tools.call(
                    "validatePlan",
                    PlanValidationRequest(
                        schemaVersion="1.0",
                        curriculumSnapshotId=plan.curriculum_snapshot_id,
                        offeringSnapshotId=plan.offering_snapshot_id,
                        academicRecordId=plan.academic_record_id,
                        mode=plan.mode,
                        items=items,
                        hardConstraints=constraints,
                    ),
                    context,
                ),
            )
            if verification.verifierResultId == plan.verifier_result_id:
                raise ReusedVerification
        plan_id = new_id("plan")
        self._plans.remember(
            session_id=session_id,
            plan_id=plan_id,
            curriculum_snapshot_id=plan.curriculum_snapshot_id,
            offering_snapshot_id=plan.offering_snapshot_id,
            academic_record_id=plan.academic_record_id,
            mode=plan.mode,
            items=items,
            hard_constraints=constraints,
            verifier_result_id=verification.verifierResultId
            if verification
            else plan.verifier_result_id,
        )
        return ReplacementResult(
            previous_plan_id=plan.plan_id,
            plan_id=plan_id,
            items=items,
            hard_constraints=constraints,
            verification=verification,
            empty=not items,
        )

    def _selected_offering(
        self,
        plan: SavedPlan,
        course_code: str,
        selected_class_id: str,
        context: ExecutionContext,
    ) -> CourseOffering:
        offerings = self._load_offerings(plan, course_code, context)
        selected = next((item for item in offerings if item.classId == selected_class_id), None)
        if selected is None:
            raise UnknownClass
        return selected

    def _load_offerings(
        self,
        plan: SavedPlan,
        course_code: str,
        context: ExecutionContext,
    ) -> list[CourseOffering]:
        self._require_snapshot(plan)
        offerings = cast(
            list[CourseOffering],
            self._tools.call(
                "listOfferings",
                None,
                context,
                params={
                    "curriculumSnapshotId": plan.curriculum_snapshot_id,
                    "offeringSnapshotId": plan.offering_snapshot_id,
                    "courseCode": course_code,
                    "limit": COURSE_OFFERING_LIMIT,
                },
            ),
        )
        return [item for item in offerings if item.courseCode == course_code]

    def _require_plan(self, session_id: str, plan_id: str) -> SavedPlan:
        plan = self._plans.get(session_id, plan_id)
        if plan is None:
            raise PlanNotInSession
        return plan

    @staticmethod
    def _require_snapshot(plan: SavedPlan) -> None:
        if plan.offering_snapshot_id is None:
            raise OfferingSnapshotMissing


def _ensure_single_course(plan: SavedPlan, course_code: str) -> None:
    matches = [item for item in plan.items if item.courseCode == course_code]
    if not matches:
        raise CourseNotInPlan("方案里没有这门课")
    if len(matches) != 1:
        raise CourseNotInPlan("方案里这门课出现了多次，不能替换")


def _replaced_items(plan: SavedPlan, course_code: str, offering: CourseOffering) -> list[PlanItem]:
    replaced: list[PlanItem] = []
    for item in plan.items:
        if item.courseCode != course_code:
            replaced.append(item.model_copy(deep=True))
            continue
        replaced.append(
            item.model_copy(
                deep=True,
                update={"classId": offering.classId, "teacherKey": offering.teacherKey},
            )
        )
    return replaced
