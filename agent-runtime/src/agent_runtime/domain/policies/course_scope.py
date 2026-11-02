"""Default course recommendation eligibility shared by planning and advice chat."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

DEFAULT_CANDIDATE_CATEGORIES = frozenset({"专业选修课", "高年级研讨课"})
# School-report outcomes that mean the student has already earned the course or is taking it.
SCHOOL_TAKEN_OUTCOMES = frozenset({"PASSED", "IN_PROGRESS"})


def eligible_course_codes(
    courses: Iterable[Any],
    record_courses: Iterable[Any],
    explicitly_selected: Iterable[str] = (),
    *,
    gap_categories: Iterable[str] = (),
    school_taken_codes: Iterable[str] = (),
) -> set[str]:
    """Return unique course codes eligible for recommendation.

    Explicit selections preserve their category-independent behavior. A passed or
    in-progress course remains excluded (from the Java record or the school report),
    and duplicate catalog codes remain ambiguous. UNKNOWN outcomes are not treated
    as completed. Categories with a school-report credit gap are eligible in addition
    to the default candidate categories.
    """
    catalog = list(courses)
    counts = Counter(course.courseCode for course in catalog)
    outcomes: dict[str, set[str]] = {}
    for record in record_courses:
        outcomes.setdefault(record.courseCode, set()).add(record.outcome)

    passed = {code for code, values in outcomes.items() if "PASSED" in values}
    in_progress = {code for code, values in outcomes.items() if "IN_PROGRESS" in values}
    taken = passed | in_progress | set(school_taken_codes)
    categories = DEFAULT_CANDIDATE_CATEGORIES | set(gap_categories)
    explicit = set(explicitly_selected)
    eligible: set[str] = set()
    for course in catalog:
        code = course.courseCode
        if counts[code] != 1 or code in taken:
            continue
        if course.category in categories or code in explicit:
            eligible.add(code)
    return eligible


def school_gap_categories(
    nodes: Iterable[Any], catalog_categories: Iterable[str]
) -> frozenset[str]:
    """Categories whose school-report node has remaining credits.

    Matching is exact on the node name against a Java catalog category. No other
    mapping is inferred, so an unmatched school node simply yields no gap category.
    """
    known = set(catalog_categories)
    return frozenset(
        node.name
        for node in nodes
        if node.name in known and node.remainingCredits is not None and node.remainingCredits > 0
    )


def school_taken_codes(snapshot_courses: Iterable[Any]) -> frozenset[str]:
    """Course codes the school report marks as PASSED or IN_PROGRESS."""
    return frozenset(
        course.courseCode for course in snapshot_courses if course.outcome in SCHOOL_TAKEN_OUTCOMES
    )
