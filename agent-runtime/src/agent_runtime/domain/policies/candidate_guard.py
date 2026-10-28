"""Rejects candidate items that reference objects outside tool-provided facts."""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.api.schemas import Issue, PlanItem, TeacherPreference


@dataclass(frozen=True)
class KnownFacts:
    """The bounded set of ids a candidate may reference (C-04/C-06)."""

    course_codes: frozenset[str] = frozenset()
    teacher_keys: frozenset[str] = frozenset()
    class_ids: frozenset[str] = frozenset()
    teacher_course_pairs: frozenset[tuple[str, str]] = frozenset()
    course_class_pairs: frozenset[tuple[str, str]] = frozenset()
    teacher_course_class_triples: frozenset[tuple[str, str, str]] = frozenset()


class CandidateGuard:
    """Model candidate ids MUST belong to the set returned by the tools.

    Never trust a fluent but invented course/teacher id (c-agent.md section 5).
    """

    def check(
        self,
        items: list[PlanItem],
        facts: KnownFacts,
        required_teacher_pairs: list[TeacherPreference] | None = None,
    ) -> list[Issue]:
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
            if (
                item.teacherKey is not None
                and facts.teacher_course_pairs
                and (item.courseCode, item.teacherKey) not in facts.teacher_course_pairs
            ):
                issues.append(
                    self._issue(
                        "TEACHER_COURSE_MISMATCH",
                        f"教师 {item.teacherKey} 未被工具确认教授课程 {item.courseCode}",
                        "teacherKey",
                    )
                )
            if (
                item.classId is not None
                and facts.course_class_pairs
                and (item.courseCode, item.classId) not in facts.course_class_pairs
            ):
                issues.append(
                    self._issue(
                        "CLASS_COURSE_MISMATCH",
                        f"班次 {item.classId} 未被工具确认属于课程 {item.courseCode}",
                        "classId",
                    )
                )
            if (
                item.teacherKey is not None
                and item.classId is not None
                and facts.teacher_course_class_triples
                and (item.courseCode, item.teacherKey, item.classId)
                not in facts.teacher_course_class_triples
            ):
                issues.append(
                    self._issue(
                        "OFFERING_BINDING_MISMATCH",
                        "课程、教师和班次的组合未被工具确认",
                        "classId",
                    )
                )

        proposed_by_course = {item.courseCode: item for item in items}
        for pin in required_teacher_pairs or []:
            if pin.mode != "MUST":
                continue
            proposed = proposed_by_course.get(pin.courseCode)
            if proposed is None or proposed.teacherKey != pin.teacherKey:
                issues.append(
                    self._issue(
                        "MUST_TEACHER_NOT_PRESERVED",
                        f"必须保留课程 {pin.courseCode} 与指定教师 {pin.teacherKey}",
                        "teacherKey",
                    )
                )
        return issues

    @staticmethod
    def _issue(code: str, message: str, field: str) -> Issue:
        return Issue(code=code, message=message, field=field, retryable=False)
