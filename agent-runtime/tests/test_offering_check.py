"""Offered-this-term check with plain fakes (application/offering_check.py)."""

from __future__ import annotations

from agent_runtime.api.schemas import CourseOffering, Meeting
from agent_runtime.application.offering_check import (
    OFFERING_PAGE_LIMIT,
    ScanResult,
    check_offerings,
)


def _row(course: str, class_id: str = "class:a") -> CourseOffering:
    return CourseOffering(
        courseCode=course,
        classId=class_id,
        teacherKey="teacher:a",
        teacherText="演示教师",
        credits=None,
        capacity=None,
        meetingTextRaw="演示",
        meetings=[Meeting(dayOfWeek=1, sectionStart=1, sectionEnd=2, weeks=[1])],
        parseStatus="PARSED",
        sourceRefId="source:demo",
    )


class _Lookups:
    """Per-course lookup fake that records calls; ``answers`` maps code to rows or None."""

    def __init__(self, answers: dict[str, list[CourseOffering] | None]) -> None:
        self._answers = answers
        self.calls: list[str] = []

    def __call__(self, code: str) -> list[CourseOffering] | None:
        self.calls.append(code)
        return self._answers.get(code, [])


class _Budget:
    def __init__(self, limit: int) -> None:
        self._left = limit
        self.taken = 0

    def __call__(self) -> bool:
        if self._left <= 0:
            return False
        self._left -= 1
        self.taken += 1
        return True


def test_complete_scan_settles_every_candidate_without_lookups() -> None:
    scan = ScanResult(rows=(_row("CS101"), _row("CS101", "class:b")), complete=True)
    lookups = _Lookups({})
    result = check_offerings(
        ["CS101", "MATH201"],
        pinned=frozenset(),
        scan=scan,
        lookup=lookups,
        take_call=_Budget(0),
        stop_after=20,
    )

    assert result.offered == {"CS101"}
    assert result.not_offered == {"MATH201"}
    assert len(result.rows_by_course["CS101"]) == 2
    assert result.known_rows() == {"CS101": list(result.rows_by_course["CS101"]), "MATH201": []}
    assert lookups.calls == []
    assert not result.budget_exhausted


def test_truncated_scan_counts_present_courses_and_looks_up_the_rest() -> None:
    scan = ScanResult(rows=(_row("CS101"),), complete=False)
    lookups = _Lookups({"MATH201": [_row("MATH201")], "PHYS101": []})
    result = check_offerings(
        ["CS101", "MATH201", "PHYS101"],
        pinned=frozenset(),
        scan=scan,
        lookup=lookups,
        take_call=_Budget(10),
        stop_after=20,
    )

    assert result.offered == {"CS101", "MATH201"}
    assert result.not_offered == {"PHYS101"}
    # CS101 is positive from the page; its full rows come back at assignment time.
    assert "CS101" not in result.rows_by_course
    assert lookups.calls == ["MATH201", "PHYS101"]


def test_stop_after_ends_lookups_for_unpinned_candidates_but_not_pinned() -> None:
    lookups = _Lookups({"A": [_row("A")], "B": [_row("B")], "C": [_row("C")], "P": [_row("P")]})
    result = check_offerings(
        ["P", "A", "B", "C"],
        pinned=frozenset({"P"}),
        scan=None,
        lookup=lookups,
        take_call=_Budget(10),
        stop_after=2,
    )

    # P is pinned and checked first; A makes two offered, so B and C are not looked up.
    assert lookups.calls == ["P", "A"]
    assert result.offered == {"P", "A"}
    assert not result.unverified_budget


def test_budget_spent_marks_remaining_candidates_unverified() -> None:
    lookups = _Lookups({"A": [_row("A")]})
    result = check_offerings(
        ["A", "B", "C"],
        pinned=frozenset(),
        scan=None,
        lookup=lookups,
        take_call=_Budget(1),
        stop_after=20,
    )

    assert result.offered == {"A"}
    assert result.unverified_budget == {"B", "C"}
    assert result.budget_exhausted
    assert lookups.calls == ["A"]


def test_failed_lookup_is_unverified_not_not_offered() -> None:
    lookups = _Lookups({"A": None})
    result = check_offerings(
        ["A"],
        pinned=frozenset(),
        scan=None,
        lookup=lookups,
        take_call=_Budget(5),
        stop_after=20,
    )

    assert result.unverified_failed == {"A"}
    assert "A" not in result.not_offered
    assert "A" not in result.offered


def test_page_limit_is_java_maximum() -> None:
    # Java rejects limit > 100 (contracts/java.openapi.json); a full page is 100 rows.
    assert OFFERING_PAGE_LIMIT == 100
