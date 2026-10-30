from decimal import Decimal

from agent_runtime.api.schemas import CompletedCourse, Course
from agent_runtime.domain.policies.course_scope import eligible_course_codes


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
