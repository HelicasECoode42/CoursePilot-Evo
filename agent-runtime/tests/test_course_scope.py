from decimal import Decimal
from types import SimpleNamespace

from agent_runtime.api.schemas import CompletedCourse, Course
from agent_runtime.domain.policies.course_scope import (
    build_course_scope,
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


def _node(node_id, parent, name, remaining, leaf=False):
    return SimpleNamespace(
        nodeId=node_id,
        parentId=parent,
        name=name,
        leaf=leaf,
        remainingCredits=None if remaining is None else Decimal(remaining),
    )


def _school(node_id, code, outcome="NOT_TAKEN"):
    return SimpleNamespace(nodeId=node_id, courseCode=code, outcome=outcome)


def test_default_scope_includes_required_and_excludes_record_taken() -> None:
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
    scope = build_course_scope(courses, records)
    assert scope.eligible == {"CORE", "ELECTIVE", "SEMINAR", "FAILED", "UNKNOWN"}
    assert scope.required == {"CORE"}
    assert scope.taken == {"PASSED", "ACTIVE"}


def test_school_in_progress_excluded_even_when_record_marks_it_otherwise() -> None:
    courses = [_course("ALG", "专业选修课"), _course("MINE", "专业选修课")]
    # The academic record says UNKNOWN (conflicting attempts); the school report says IN_PROGRESS.
    records = [_record("ALG", "UNKNOWN")]
    school_rows = [SimpleNamespace(courseCode="ALG", outcome="IN_PROGRESS")]
    scope = build_course_scope(courses, records, school_taken=school_taken_codes(school_rows))
    assert scope.eligible == {"MINE"}
    assert "ALG" in scope.taken


def test_explicit_selection_keeps_nondefault_category_but_not_taken() -> None:
    courses = [
        _course("PUBLIC", "公共基础课"),
        _course("PASSED", "专业选修课"),
        _course("ACTIVE", "学科基础课"),
    ]
    records = [_record("PASSED", "PASSED"), _record("ACTIVE", "IN_PROGRESS")]
    scope = build_course_scope(courses, records, explicitly_selected={"PUBLIC", "PASSED", "ACTIVE"})
    assert scope.eligible == {"PUBLIC"}


def test_ambiguous_catalog_code_is_not_eligible_even_when_selected() -> None:
    courses = [_course("DUP", "专业选修课"), _course("DUP", "高年级研讨课")]
    assert build_course_scope(courses, [], explicitly_selected={"DUP"}).eligible == frozenset()


def test_gap_targets_deepest_leaf_only_not_the_parent_category() -> None:
    courses = [
        _course("MOral", "公共基础课"),
        _course("MATH", "公共基础课"),
        _course("SPORT", "公共基础课"),
    ]
    # 公共基础课 (parent, gap 1) -> 思想政治必修课 (leaf, gap 1, school links MOral) ; 体育 done.
    nodes = [
        _node("n:pub", None, "公共基础课", "1"),
        _node("n:ideo", "n:pub", "思想政治必修课", "1", leaf=True),
        _node("n:sport", "n:pub", "体育", "0", leaf=True),
    ]
    school = [_school("n:ideo", "MOral"), _school("n:sport", "SPORT", "PASSED")]
    scope = build_course_scope(courses, [], school_nodes=nodes, school_courses=school)
    assert scope.eligible == {"MOral"}
    assert [(leaf.name, leaf.remaining_credits) for leaf in scope.gap_leaves] == [
        ("思想政治必修课", "1")
    ]
    leaf = scope.gap_leaf_for("MOral")
    assert leaf is not None and leaf.name == "思想政治必修课"
    assert scope.gap_leaf_for("MATH") is None


def test_leaf_with_exact_category_name_takes_that_category_only() -> None:
    courses = [_course("CORE1", "学科基础课"), _course("ELEC", "专业选修课")]
    nodes = [_node("n:core", None, "学科基础课", "5", leaf=True)]
    scope = build_course_scope(courses, [], school_nodes=nodes, school_courses=[])
    assert scope.gap_leaves[0].course_codes == {"CORE1"}
    assert scope.eligible == {"CORE1", "ELEC"}
    assert scope.required == {"CORE1"}


def test_school_gap_requires_exact_name_and_positive_remaining() -> None:
    courses = [_course("CORE", "学科基础课"), _course("ELEC", "专业选修课")]
    nodes = [
        _node("n:a", None, "学科基础", "5", leaf=True),
        _node("n:b", None, "专业选修课", None, leaf=True),
        _node("n:c", None, "实践教学环节", "0", leaf=True),
    ]
    scope = build_course_scope(courses, [], school_nodes=nodes, school_courses=[])
    # 学科基础 matches no catalog category and has no school links: no gap target.
    assert scope.gap_leaves == ()
    assert scope.eligible == {"CORE", "ELEC"}


def test_parent_gap_without_gapped_child_stays_parent_and_expands_nothing() -> None:
    courses = [_course("PUB", "公共基础课")]
    nodes = [_node("n:pub", None, "公共基础课", "2")]
    scope = build_course_scope(courses, [], school_nodes=nodes, school_courses=[])
    # Not a leaf, so the exact category name does not expand it; no school links exist.
    assert scope.gap_leaves == ()
    assert scope.eligible == frozenset()
