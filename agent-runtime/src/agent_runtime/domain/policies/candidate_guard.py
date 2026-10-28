"""Rejects candidate items that reference objects outside tool-provided facts."""

from __future__ import annotations

from dataclasses import dataclass

from agent_runtime.api.schemas import Issue, PlanItem, TeacherPreference


@dataclass(frozen=True)
class CourseFact:
    """课程的描述属性，只用于给模型理解事实，不参与准入判断。

    没有这些属性时，模型拿到的只有课程号，无法把学生说的「Java 程序设计」对应到
    某个 courseCode，也无法对着核对缺口判断学分和类别——只能反问。
    """

    course_code: str
    name: str
    credits: str | None
    category: str


@dataclass(frozen=True)
class ReviewFact:
    """一条评价证据。excerpt 是外部文本，按不可信数据对待（截断、限量、标注）。"""

    review_note_id: str
    course_code: str
    teacher_display_name: str | None
    match_status: str
    dimensions: tuple[str, ...]
    excerpt: str
    source_ref_id: str


@dataclass(frozen=True)
class KnownFacts:
    """The bounded set of ids a candidate may reference (C-04/C-06).

    ``course_facts`` 与 ``review_facts`` 是描述性的，CandidateGuard 从不读它们：
    准入只看 id 集合，描述属性不能放宽任何一条准入规则。
    """

    course_codes: frozenset[str] = frozenset()
    taken_course_codes: frozenset[str] = frozenset()
    teacher_keys: frozenset[str] = frozenset()
    class_ids: frozenset[str] = frozenset()
    teacher_course_pairs: frozenset[tuple[str, str]] = frozenset()
    course_class_pairs: frozenset[tuple[str, str]] = frozenset()
    teacher_course_class_triples: frozenset[tuple[str, str, str]] = frozenset()
    course_facts: tuple[CourseFact, ...] = ()
    review_facts: tuple[ReviewFact, ...] = ()
    reviews_queried_for: frozenset[str] = frozenset()


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
            if item.courseCode in facts.taken_course_codes:
                issues.append(
                    self._issue(
                        "COURSE_ALREADY_TAKEN",
                        f"课程 {item.courseCode} 已在学业记录中",
                        "courseCode",
                    )
                )
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
