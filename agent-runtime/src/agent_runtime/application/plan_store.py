"""Session-owned plans remembered for a later class replacement.

Plans are keyed by plan id. A lookup always takes the current session, so one
session cannot read or replace another session's plan. This store does not
decide conflicts; Java does that through ``validatePlan``.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from agent_runtime.api.schemas import Constraint, PlanItem, PlanningMode


class PlanNotInSession(Exception):
    """The plan id is unknown here, including a plan owned by another session."""


@dataclass(frozen=True)
class SavedPlan:
    plan_id: str
    session_id: str
    curriculum_snapshot_id: str
    offering_snapshot_id: str | None
    academic_record_id: str
    mode: PlanningMode
    items: tuple[PlanItem, ...]
    hard_constraints: tuple[Constraint, ...]
    verifier_result_id: str


class SessionPlanStore:
    """In-memory plan index. The first writer of a plan id keeps it."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._plans: dict[str, SavedPlan] = {}

    def remember(
        self,
        *,
        session_id: str,
        plan_id: str,
        curriculum_snapshot_id: str,
        offering_snapshot_id: str | None,
        academic_record_id: str,
        mode: PlanningMode,
        items: list[PlanItem],
        hard_constraints: list[Constraint],
        verifier_result_id: str,
    ) -> None:
        saved = SavedPlan(
            plan_id=plan_id,
            session_id=session_id,
            curriculum_snapshot_id=curriculum_snapshot_id,
            offering_snapshot_id=offering_snapshot_id,
            academic_record_id=academic_record_id,
            mode=mode,
            items=tuple(item.model_copy(deep=True) for item in items),
            hard_constraints=tuple(item.model_copy(deep=True) for item in hard_constraints),
            verifier_result_id=verifier_result_id,
        )
        with self._lock:
            self._plans.setdefault(plan_id, saved)

    def get(self, session_id: str, plan_id: str) -> SavedPlan | None:
        with self._lock:
            saved = self._plans.get(plan_id)
        if saved is None or saved.session_id != session_id:
            return None
        return saved

    def plan_ids(self, session_id: str) -> list[str]:
        with self._lock:
            return [plan.plan_id for plan in self._plans.values() if plan.session_id == session_id]
