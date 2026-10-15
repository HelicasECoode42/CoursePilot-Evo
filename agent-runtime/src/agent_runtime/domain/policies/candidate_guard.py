"""Rejects candidate items that reference objects outside tool-provided facts."""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.api.schemas import Issue, PlanItem


@dataclass(frozen=True)
class KnownFacts:
    """The bounded set of ids a candidate may reference (C-04/C-06)."""

    course_codes: frozenset[str] = frozenset()
    teacher_keys: frozenset[str] = frozenset()
    class_ids: frozenset[str] = frozenset()


class CandidateGuard:
    """Model candidate ids MUST belong to the set returned by the tools.

    Never trust a fluent but invented course/teacher id (c-agent.md section 5).
    """

    def check(self, items: list[PlanItem], facts: KnownFacts) -> list[Issue]:
        issues: list[Issue] = []
        for item in items:
            if item.courseCode not in facts.course_codes:
                issues.append(
                    self._issue(
                        "UNKNOWN_COURSE", f"课程 {item.courseCode} 不在当前快照", "courseCode"
                    )
                )
            if item.teacherKey is not None and item.teacherKey not in facts.teacher_keys:
                issues.append(
                    self._issue(
                        "UNKNOWN_TEACHER", f"教师 {item.teacherKey} 不在当前事实", "teacherKey"
                    )
                )
            if item.classId is not None and item.classId not in facts.class_ids:
                issues.append(
                    self._issue("UNKNOWN_CLASS", f"班次 {item.classId} 不在当前快照", "classId")
                )
        return issues

    @staticmethod
    def _issue(code: str, message: str, field: str) -> Issue:
        return Issue(code=code, message=message, field=field, retryable=False)
