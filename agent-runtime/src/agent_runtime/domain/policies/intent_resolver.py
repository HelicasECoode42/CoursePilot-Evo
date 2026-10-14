"""Pure decision: does the request carry enough goal to plan, or do we ask first?"""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.api.schemas import PlanningRequest

_TIME_KINDS = {"BLOCK_DAY", "BLOCK_SECTION", "BLOCK_SLOT"}
_TEACHER_PRIORITY = {"SPECIFIC_TEACHER", "PIN_TEACHER", "TEACHER"}
_SCHEDULE_PRIORITY = {"SCHEDULE"}


@dataclass(frozen=True)
class ResolvedIntent:
    needs_clarification: bool
    missing: tuple[str, ...]


class IntentResolver:
    """Deterministic gates before the model loop (C-01/C-02/C-03).

    Full motive understanding is a model concern; this only decides whether we
    must ask one question first. MUST teacher + hard time without a ranked
    tradeoff is asked, never silently dropping the teacher.
    """

    def resolve(self, request: PlanningRequest) -> ResolvedIntent:
        intent = request.intent
        missing: list[str] = []
        if (
            not intent.motives
            and not intent.hardConstraints
            and not intent.pinnedTeacherCoursePairs
        ):
            missing.append("motives")
        if not intent.priorityOrder:
            missing.append("priorityOrder")
        must_pins = [pair for pair in intent.pinnedTeacherCoursePairs if pair.mode == "MUST"]
        hard_time = [item for item in intent.hardConstraints if item.kind in _TIME_KINDS]
        ranked = {item.upper() for item in intent.priorityOrder}
        teacher_ranked = bool(ranked & _TEACHER_PRIORITY)
        schedule_ranked = bool(ranked & _SCHEDULE_PRIORITY)
        if must_pins and hard_time and not (teacher_ranked and schedule_ranked):
            missing.append("teacher_vs_schedule")
        return ResolvedIntent(needs_clarification=bool(missing), missing=tuple(missing))
