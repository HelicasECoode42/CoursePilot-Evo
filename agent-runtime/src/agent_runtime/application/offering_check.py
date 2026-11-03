"""Which candidate courses are offered in the plan's offering snapshot (module C).

Java's ``listOfferings`` takes at most one ``courseCode`` per call (or no code, with a
page of at most 100 rows) and has no cursor. So the check combines two kinds of lookup:

- one unfiltered page. A short page (fewer than ``OFFERING_PAGE_LIMIT`` rows) lists the
  whole snapshot, so every candidate is then verified without further calls. A full page
  only proves that the courses it contains are offered; it cannot prove absence.
- one call per remaining candidate, in the order given (pinned courses first, then the
  runner's relevance order), until ``stop_after`` offered candidates are found or the
  precheck call budget is spent.

Only ``offered`` candidates may reach the model or be recommended. A pinned course that
is not offered is kept by the runner and reported as not offered; an unverified course
is not recommended. This module does no I/O: the caller passes the lookups and the
budget as callables, so the decision logic can be tested with plain fakes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from agent_runtime.api.schemas import CourseOffering

# Java's listOfferings upper bound for ``limit`` without a courseCode (contracts/java.openapi.json).
OFFERING_PAGE_LIMIT = 100
# Upper bound for ``limit`` with one courseCode: every section of that course in one call.
# Java has no cursor, so a result of exactly this many rows may be incomplete.
COURSE_OFFERING_LIMIT = 1000


@dataclass(frozen=True)
class ScanResult:
    """Rows of the unfiltered listOfferings page, and whether that page is the whole snapshot."""

    rows: tuple[CourseOffering, ...]
    complete: bool


@dataclass(frozen=True)
class OfferingCheck:
    offered: frozenset[str] = frozenset()
    not_offered: frozenset[str] = frozenset()
    # Candidates not verified because the precheck call budget ran out.
    unverified_budget: frozenset[str] = frozenset()
    # Candidates whose lookup failed (Java unavailable or rejected the call).
    unverified_failed: frozenset[str] = frozenset()
    # Full rows, only for candidates verified by a per-course lookup or a complete scan.
    rows_by_course: Mapping[str, tuple[CourseOffering, ...]] = field(default_factory=dict)

    def known_rows(self) -> dict[str, list[CourseOffering]]:
        """Rows usable for section assignment without another call; empty list = not offered."""
        rows: dict[str, list[CourseOffering]] = {
            code: list(values) for code, values in self.rows_by_course.items()
        }
        for code in self.not_offered:
            rows[code] = []
        return rows

    @property
    def budget_exhausted(self) -> bool:
        return bool(self.unverified_budget)


def _group(rows: Iterable[CourseOffering]) -> dict[str, list[CourseOffering]]:
    grouped: dict[str, list[CourseOffering]] = {}
    for row in rows:
        grouped.setdefault(row.courseCode, []).append(row)
    return grouped


def check_offerings(
    candidates: Sequence[str],
    *,
    pinned: frozenset[str],
    scan: ScanResult | None,
    lookup: Callable[[str], Sequence[CourseOffering] | None],
    take_call: Callable[[], bool],
    stop_after: int,
) -> OfferingCheck:
    """Decide offered / not offered for ``candidates`` (already in priority order).

    ``lookup(code)`` returns the snapshot rows for one course, or ``None`` when the call
    failed. ``take_call()`` reserves one call from the precheck budget and returns False
    when none is left. Pinned candidates are always looked up while budget remains;
    other candidates stop being looked up once ``stop_after`` are offered.
    """
    if scan is not None:
        by_code = _group(scan.rows)
        if scan.complete:
            offered = {code for code in candidates if code in by_code}
            return OfferingCheck(
                offered=frozenset(offered),
                not_offered=frozenset(code for code in candidates if code not in by_code),
                rows_by_course={code: tuple(by_code[code]) for code in offered},
            )
        present = {code for code in candidates if code in by_code}
    else:
        present = set()

    offered: set[str] = set(present)
    not_offered: set[str] = set()
    rows_by_course: dict[str, tuple[CourseOffering, ...]] = {}
    unverified_budget: set[str] = set()
    unverified_failed: set[str] = set()
    for code in candidates:
        if code in offered or code in not_offered:
            continue
        if len(offered) >= stop_after and code not in pinned:
            continue
        if not take_call():
            unverified_budget.add(code)
            continue
        rows = lookup(code)
        if rows is None:
            unverified_failed.add(code)
            continue
        matching = tuple(row for row in rows if row.courseCode == code)
        if matching:
            offered.add(code)
            rows_by_course[code] = matching
        else:
            not_offered.add(code)
    return OfferingCheck(
        offered=frozenset(offered),
        not_offered=frozenset(not_offered),
        unverified_budget=frozenset(unverified_budget),
        unverified_failed=frozenset(unverified_failed),
        rows_by_course=rows_by_course,
    )
