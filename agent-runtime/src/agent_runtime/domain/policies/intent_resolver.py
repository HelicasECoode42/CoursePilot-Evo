"""Pure decision: does the request carry enough goal to plan, or do we ask first?"""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.api.schemas import PlanningRequest


@dataclass(frozen=True)
class ResolvedIntent:
    needs_clarification: bool
    missing: tuple[str, ...]


class IntentResolver:
    """W1 policy: decide whether any goal signal exists at all (C-01/C-02).

    Full motive understanding is a model concern (W2/W3); this only gates the
    clarify-vs-plan branch with a deterministic, testable rule.
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
        return ResolvedIntent(needs_clarification=bool(missing), missing=tuple(missing))
