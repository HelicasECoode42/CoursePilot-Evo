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
    Constraint,
    CourseOffering,
    PlanItem,
    PlanValidation,
    PlanValidationRequest,
)
from agent_runtime.application.context import ExecutionContext
from agent_runtime.application.ids import new_id
from agent_runtime.application.plan_store import PlanNotInSession, SavedPlan, SessionPlanStore


class CourseNotInPlan(Exception):
    """The saved plan does not contain exactly one item for the target course."""


class UnknownClass(Exception):
    """The selected class is not in this course's current offering query."""


class OfferingSnapshotMissing(Exception):
    """The saved plan has no offering snapshot, so a class search cannot run."""


class ReusedVerification(Exception):
    """Java returned the previous verifier result id. That verdict is not new."""


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
