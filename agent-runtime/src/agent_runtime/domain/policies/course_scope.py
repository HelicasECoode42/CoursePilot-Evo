"""Default course recommendation eligibility shared by planning and advice chat.

Rules (docs/38 section 6):
- A course is a candidate only if it is in a default elective category, in a
  category the curriculum states as required (学科基础课), inside a school-report
  sub-category that still has credits missing, or explicitly selected by the student.
- PASSED and IN_PROGRESS courses are never candidates. They come from the Java
  academic record and from the school report. The school report counts even when
  its record id differs from the request, because the taken status is a fact about
  the student, not about one record revision.
- School-report gaps are read at the deepest node that still has credits missing,
  so 公共基础课 with 思想政治必修课 remaining 1 targets only that sub-category.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CANDIDATE_CATEGORIES = frozenset({"专业选修课", "高年级研讨课"})
# School-report outcomes that mean the student has already earned the course or is taking it.
SCHOOL_TAKEN_OUTCOMES = frozenset({"PASSED", "IN_PROGRESS"})


# Requirement nature by curriculum category. Only categories whose nature the
# curriculum file states are mapped; anything else is None and never guessed.
_REQUIREMENT_NATURE = {
    "学科基础课": "必修",
    "专业选修课": "选修",
}
# Categories the curriculum states as required. Their courses are candidates and are
# placed first in a plan when offered this term.
REQUIRED_CATEGORIES = frozenset(c for c, nature in _REQUIREMENT_NATURE.items() if nature == "必修")


@dataclass(frozen=True)
class GapLeaf:
    """One school-report sub-category that still has credits missing.

    ``course_codes`` are the catalog codes that belong to it: school-linked rows of
    that node, plus the catalog courses of the exact category name when the node is
    a school leaf whose name matches a catalog category. Parents are never expanded.
    """

    node_id: str
    name: str
    remaining_credits: str
    course_codes: frozenset[str]


@dataclass(frozen=True)
class CourseScope:
    eligible: frozenset[str]
    required: frozenset[str]
    taken: frozenset[str]
    gap_leaves: tuple[GapLeaf, ...] = ()
    gap_by_code: Mapping[str, GapLeaf] = field(default_factory=dict, compare=False)

    def gap_leaf_for(self, course_code: str) -> GapLeaf | None:
        return self.gap_by_code.get(course_code)


def school_leaf_gaps(
    nodes: Iterable[Any],
    school_courses: Iterable[Any],
    catalog_codes_by_category: Mapping[str, set[str]],
) -> tuple[GapLeaf, ...]:
    """Deepest school nodes with remaining credits that have catalog courses to offer.

    A node with remaining credits is a target only when none of its descendants also
    has remaining credits, so a parent is never a target while a child still needs
    credits. Course codes are kept only when they exist in the catalog, and a node with
    no such code is dropped: the report cannot be turned into a recommendation there.
    Matching to catalog categories is exact on the node name.
    """
    catalog_codes = set().union(*catalog_codes_by_category.values())
    node_list = list(nodes)
    gapped = {
        node.nodeId
        for node in node_list
        if node.remainingCredits is not None and node.remainingCredits > 0
    }
    children: dict[str, list[str]] = {}
    for node in node_list:
        if node.parentId is not None:
            children.setdefault(node.parentId, []).append(node.nodeId)

    def has_gapped_descendant(node_id: str, seen: frozenset[str]) -> bool:
        for child in children.get(node_id, []):
            if child in seen:
                continue
            if child in gapped or has_gapped_descendant(child, seen | {child}):
                return True
        return False

    school_linked: dict[str, set[str]] = {}
    for row in school_courses:
        school_linked.setdefault(row.nodeId, set()).add(row.courseCode)

    leaves: list[GapLeaf] = []
    for node in node_list:
        if node.nodeId not in gapped or has_gapped_descendant(
            node.nodeId, frozenset({node.nodeId})
        ):
            continue
        codes = set(school_linked.get(node.nodeId, set()))
        if node.leaf and node.name in catalog_codes_by_category:
            codes |= catalog_codes_by_category[node.name]
        codes &= catalog_codes
        if not codes:
            continue
        leaves.append(
            GapLeaf(
                node_id=node.nodeId,
                name=node.name,
                remaining_credits=str(node.remainingCredits),
                course_codes=frozenset(codes),
            )
        )
    return tuple(leaves)


def build_course_scope(
    courses: Iterable[Any],
    record_courses: Iterable[Any],
    *,
    school_taken: Iterable[str] = (),
    school_nodes: Iterable[Any] = (),
    school_courses: Iterable[Any] = (),
    explicitly_selected: Iterable[str] = (),
) -> CourseScope:
    """Candidate set, required set and school gap leaves for one planning turn.

    ``school_taken`` is applied regardless of record matching. ``school_nodes`` and
    ``school_courses`` should be passed only when the school report matches this
    curriculum and record; they drive the sub-category gaps.
    """
    catalog = list(courses)
    counts = Counter(course.courseCode for course in catalog)
    outcomes: dict[str, set[str]] = {}
    for record in record_courses:
        outcomes.setdefault(record.courseCode, set()).add(record.outcome)

    passed = {code for code, values in outcomes.items() if "PASSED" in values}
    in_progress = {code for code, values in outcomes.items() if "IN_PROGRESS" in values}
    taken = frozenset(passed | in_progress | set(school_taken))

    catalog_by_category: dict[str, set[str]] = {}
    for course in catalog:
        catalog_by_category.setdefault(course.category, set()).add(course.courseCode)
    gap_leaves = school_leaf_gaps(school_nodes, school_courses, catalog_by_category)
    gap_by_code: dict[str, GapLeaf] = {}
    for leaf in gap_leaves:
        for code in sorted(leaf.course_codes):
            gap_by_code.setdefault(code, leaf)

    categories = DEFAULT_CANDIDATE_CATEGORIES | REQUIRED_CATEGORIES
    explicit = set(explicitly_selected)
    eligible: set[str] = set()
    required: set[str] = set()
    for course in catalog:
        code = course.courseCode
        if counts[code] != 1 or code in taken:
            continue
        if course.category in categories or code in explicit or code in gap_by_code:
            eligible.add(code)
            if course.category in REQUIRED_CATEGORIES:
                required.add(code)
    return CourseScope(
        eligible=frozenset(eligible),
        required=frozenset(required),
        taken=taken,
        gap_leaves=gap_leaves,
        gap_by_code=gap_by_code,
    )


def requirement_nature(category: str) -> str | None:
    """「必修」「选修」or None when the category does not state it."""
    return _REQUIREMENT_NATURE.get(category)


def school_taken_codes(snapshot_courses: Iterable[Any]) -> frozenset[str]:
    """Course codes the school report marks as PASSED or IN_PROGRESS."""
    return frozenset(
        course.courseCode for course in snapshot_courses if course.outcome in SCHOOL_TAKEN_OUTCOMES
    )
