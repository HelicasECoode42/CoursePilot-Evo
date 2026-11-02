"""Default course recommendation eligibility shared by planning and advice chat."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

DEFAULT_CANDIDATE_CATEGORIES = frozenset({"专业选修课", "高年级研讨课"})


def eligible_course_codes(
    courses: Iterable[Any],
    record_courses: Iterable[Any],
    explicitly_selected: Iterable[str] = (),
) -> set[str]:
    """Return unique course codes eligible for recommendation.

    Explicit selections preserve their category-independent behavior. A passed
    course remains excluded, and duplicate catalog codes remain ambiguous.
    UNKNOWN outcomes are not treated as completed.
    """
    catalog = list(courses)
    counts = Counter(course.courseCode for course in catalog)
    outcomes: dict[str, set[str]] = {}
    for record in record_courses:
        outcomes.setdefault(record.courseCode, set()).add(record.outcome)

    passed = {code for code, values in outcomes.items() if "PASSED" in values}
    in_progress = {code for code, values in outcomes.items() if "IN_PROGRESS" in values}
    explicit = set(explicitly_selected)
    eligible: set[str] = set()
    for course in catalog:
        code = course.courseCode
        if counts[code] != 1 or code in passed or code in in_progress:
            continue
        if course.category in DEFAULT_CANDIDATE_CATEGORIES or code in explicit:
            eligible.add(code)
    return eligible
