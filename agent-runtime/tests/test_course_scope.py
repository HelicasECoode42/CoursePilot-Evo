from decimal import Decimal
from types import SimpleNamespace

from agent_runtime.api.schemas import CompletedCourse, Course
from agent_runtime.domain.policies.course_scope import (
    eligible_course_codes,
    school_gap_categories,
    school_taken_codes,
)


def _course(code: str, category: str) -> Course:
    return Course(
        courseCode=code,
        name=code,
        credits=Decimal("3"),
        category=category,
        sourceRefIds=["source:test"],
    )


def _record(code: str, outcome: str) -> CompletedCourse:
    return CompletedCourse(
        courseCode=code,
        outcome=outcome,
        earnedCredits=Decimal("3") if outcome == "PASSED" else None,
        completedTerm=None,
    )


def test_default_scope_and_record_outcomes() -> None:
    courses = [
        _course("PUBLIC", "公共基础课"),
        _course("CORE", "学科基础课"),
        _course("PRACTICE", "实践教学环节"),
        _course("ELECTIVE", "专业选修课"),
        _course("SEMINAR", "高年级研讨课"),
        _course("PASSED", "专业选修课"),
        _course("ACTIVE", "专业选修课"),
        _course("FAILED", "专业选修课"),
        _course("UNKNOWN", "专业选修课"),
    ]
    records = [
        _record("PASSED", "PASSED"),
        _record("ACTIVE", "IN_PROGRESS"),
        _record("FAILED", "FAILED"),
        _record("UNKNOWN", "UNKNOWN"),
    ]

    assert eligible_course_codes(courses, records) == {
        "ELECTIVE",
        "SEMINAR",
        "FAILED",
        "UNKNOWN",
    }


def test_explicit_selection_preserves_nondefault_category_without_recommending_taken() -> None:
    courses = [
        _course("PUBLIC", "公共基础课"),
        _course("PASSED", "专业选修课"),
        _course("ACTIVE", "学科基础课"),
    ]
    records = [_record("PASSED", "PASSED"), _record("ACTIVE", "IN_PROGRESS")]

    assert eligible_course_codes(courses, records, {"PUBLIC", "PASSED", "ACTIVE"}) == {
        "PUBLIC",
    }


def test_ambiguous_catalog_code_is_not_eligible_even_when_selected() -> None:
    courses = [_course("DUP", "专业选修课"), _course("DUP", "高年级研讨课")]
    assert eligible_course_codes(courses, [], {"DUP"}) == set()


def test_gap_categories_extend_scope_and_school_taken_codes_are_excluded() -> None:
    courses = [
        _course("CORE", "学科基础课"),
        _course("CORE_DONE", "学科基础课"),
        _course("PUBLIC", "公共基础课"),
    ]
    snapshot_courses = [SimpleNamespace(courseCode="CORE_DONE", outcome="PASSED")]
    taken = school_taken_codes(snapshot_courses)
    gaps = school_gap_categories(
        [
            SimpleNamespace(name="学科基础课", remainingCredits=Decimal("34")),
            SimpleNamespace(name="公共基础课", remainingCredits=Decimal("0")),
            SimpleNamespace(name="不存在的类别", remainingCredits=Decimal("3")),
        ],
        {c.category for c in courses},
    )
    assert gaps == frozenset({"学科基础课"})
    assert eligible_course_codes(courses, [], gap_categories=gaps, school_taken_codes=taken) == {
        "CORE"
    }


def test_school_gap_requires_exact_name_and_positive_remaining() -> None:
    nodes = [
        SimpleNamespace(name="学科基础", remainingCredits=Decimal("5")),
        SimpleNamespace(name="专业选修课", remainingCredits=None),
        SimpleNamespace(name="实践教学环节", remainingCredits=Decimal("0")),
    ]
    assert school_gap_categories(nodes, {"学科基础课", "专业选修课", "实践教学环节"}) == frozenset()
    assert school_taken_codes([SimpleNamespace(courseCode="A", outcome="IN_PROGRESS")]) == {"A"}
