"""Pure section-assignment rules: conflicts, pins, parsed-first, blocks, fallback."""

from __future__ import annotations

from agent_runtime.api.schemas import Constraint, CourseOffering, Meeting, SoftPreference
from agent_runtime.application.budget import Budget, BudgetExceeded, BudgetTracker
from agent_runtime.application.section_assignment import (
    REASON_NO_OFFERING,
    REASON_TEACHER_NO_OFFERING,
    REASON_UNPARSED,
    CourseNeed,
    SectionOption,
    choose_sections,
    course_options,
    hard_blocks,
    sections_conflict,
    soft_blocks,
)


def _meeting(day: int, start: int, end: int, weeks: range = range(1, 17)) -> Meeting:
    return Meeting(dayOfWeek=day, sectionStart=start, sectionEnd=end, weeks=list(weeks))


def _offering(
    course: str,
    class_id: str,
    *,
    teacher: str | None = "teacher:a",
    meetings: list[Meeting] | None = None,
    parse: str = "PARSED",
) -> CourseOffering:
    return CourseOffering(
        courseCode=course,
        classId=class_id,
        teacherKey=teacher,
        teacherText="演示教师",
        credits=None,
        capacity=None,
        meetingTextRaw="演示",
        meetings=meetings if meetings is not None else [_meeting(1, 1, 2)],
        parseStatus=parse,
        sourceRefId="source:demo",
    )


def _option(class_id: str, *meetings: Meeting, course: str = "CS101") -> SectionOption:
    return SectionOption(
        class_id=class_id,
        course_code=course,
        teacher_key=None,
        meetings=tuple(meetings),
        soft_hits=0,
        review_count=0,
    )


def _need(course: str = "CS101", **kwargs) -> CourseNeed:
    return CourseNeed(
        course_code=course,
        item_teacher_key=kwargs.get("item"),
        must_teacher_key=kwargs.get("must"),
        prefer_teacher_key=kwargs.get("prefer"),
    )


def test_sections_conflict_only_on_shared_day_section_and_week() -> None:
    mon_1_2 = _option("a", _meeting(1, 1, 2))
    mon_2_3 = _option("b", _meeting(1, 2, 3))
    tue_1_2 = _option("c", _meeting(2, 1, 2))
    other_weeks = _option("d", _meeting(1, 1, 2, weeks=range(17, 20)))
    assert sections_conflict(mon_1_2, mon_2_3)
    assert not sections_conflict(mon_1_2, tue_1_2)
    assert not sections_conflict(mon_1_2, other_weeks)


def test_no_offerings_for_course_gives_reason() -> None:
    result = course_options(_need(), [], (), (), {})
    assert result.options == ()
    assert result.reason == REASON_NO_OFFERING


def test_must_teacher_filters_sections_and_missing_teacher_has_reason() -> None:
    rows = [
        _offering("CS101", "class:cs101-a", teacher="teacher:a"),
        _offering("CS101", "class:cs101-b", teacher="teacher:b", meetings=[_meeting(2, 3, 4)]),
    ]
    picked = course_options(_need(must="teacher:b"), rows, (), (), {})
    assert [o.class_id for o in picked.options] == ["class:cs101-b"]

    missing = course_options(_need(must="teacher:z"), rows, (), (), {})
    assert missing.options == ()
    assert missing.reason == REASON_TEACHER_NO_OFFERING


def test_unparsed_sections_are_never_offered_when_nothing_is_parsed() -> None:
    rows = [_offering("CS101", "class:cs101-a", parse="UNPARSED", meetings=[])]
    result = course_options(_need(), rows, (), (), {})
    assert result.options == ()
    assert result.reason == REASON_UNPARSED


def test_parsed_section_is_preferred_and_unparsed_one_is_dropped() -> None:
    rows = [
        _offering("CS101", "class:cs101-a", parse="UNPARSED", meetings=[]),
        _offering("CS101", "class:cs101-b", meetings=[_meeting(2, 1, 2)]),
    ]
    result = course_options(_need(), rows, (), (), {})
    assert [o.class_id for o in result.options] == ["class:cs101-b"]


def test_hard_blocks_remove_sections_and_soft_blocks_only_reorder() -> None:
    rows = [
        _offering("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)]),
        _offering("CS101", "class:cs101-b", meetings=[_meeting(3, 1, 2)]),
        _offering("CS101", "class:cs101-c", meetings=[_meeting(4, 5, 6)]),
    ]
    hard = hard_blocks(
        [
            Constraint(
                kind="BLOCK_DAY",
                courseCode=None,
                teacherKey=None,
                dayOfWeek=1,
                section=None,
                value=None,
                sourceText="周一不上课",
            )
        ]
    )
    soft = soft_blocks(
        [
            SoftPreference(
                dimension="schedule.blocked_slot", value="3-1", sourceText="尽量不排周三第一节"
            )
        ]
    )
    result = course_options(_need(), rows, hard, soft, {})
    # Monday section is removed by the hard block; the soft Wednesday hit sorts last.
    assert [o.class_id for o in result.options] == ["class:cs101-c", "class:cs101-b"]


def test_all_sections_hard_blocked_gives_reason() -> None:
    rows = [_offering("CS101", "class:cs101-a", meetings=[_meeting(1, 1, 2)])]
    hard = hard_blocks(
        [
            Constraint(
                kind="BLOCK_SLOT",
                courseCode=None,
                teacherKey=None,
                dayOfWeek=1,
                section=2,
                value=None,
                sourceText="周一第二节不上课",
            )
        ]
    )
    result = course_options(_need(), rows, hard, (), {})
    assert result.options == ()
    assert result.reason is not None and "必避时段" in result.reason


def test_review_coverage_breaks_ties_before_class_id() -> None:
    rows = [
        _offering("CS101", "class:cs101-a", teacher="teacher:a", meetings=[_meeting(1, 1, 2)]),
        _offering("CS101", "class:cs101-b", teacher="teacher:b", meetings=[_meeting(2, 1, 2)]),
    ]
    result = course_options(_need(), rows, (), (), {"teacher:b": 3, "teacher:a": 0})
    assert [o.class_id for o in result.options] == ["class:cs101-b", "class:cs101-a"]


def test_prefer_teacher_orders_first_without_filtering() -> None:
    rows = [
        _offering("CS101", "class:cs101-a", teacher="teacher:a", meetings=[_meeting(1, 1, 2)]),
        _offering("CS101", "class:cs101-b", teacher="teacher:b", meetings=[_meeting(2, 1, 2)]),
    ]
    result = course_options(_need(prefer="teacher:b"), rows, (), (), {})
    assert [o.class_id for o in result.options] == ["class:cs101-b", "class:cs101-a"]


def test_choose_sections_finds_full_assignment_where_greedy_fails() -> None:
    # Greedy takes X for slot 1 and then cannot place Z; the search swaps to Y.
    x = _option("x", _meeting(1, 1, 2), course="A")
    y = _option("y", _meeting(2, 1, 2), course="A")
    z = _option("z", _meeting(1, 1, 2), course="B")
    picks = choose_sections([[x, y], [z]])
    assert [p.class_id if p else None for p in picks] == ["y", "z"]


def test_choose_sections_leaves_minimal_slot_empty_when_impossible() -> None:
    first = _option("a", _meeting(1, 1, 2), course="A")
    second = _option("b", _meeting(1, 2, 3), course="B")
    picks = choose_sections([[first], [second]])
    assert [p.class_id if p else None for p in picks] == ["a", None]


def test_choose_sections_node_limit_still_returns_greedy_seed() -> None:
    first = _option("a", _meeting(1, 1, 2), course="A")
    second = _option("b", _meeting(1, 1, 2), course="B")
    picks = choose_sections([[first], [second]], node_limit=1)
    assert sum(1 for p in picks if p is not None) == 1


def test_offering_lookups_count_apart_from_tool_calls() -> None:
    tracker = BudgetTracker(Budget(max_offering_calls=2))
    tracker.record_offering_call({"listOfferings": 4})
    tracker.record_offering_call({"listOfferings": 4})
    assert tracker.tool_calls == 0
    assert tracker.offering_calls == 2
    try:
        tracker.record_offering_call({"listOfferings": 4})
    except BudgetExceeded as exc:
        assert "maxOfferingCalls" in str(exc)
    else:
        raise AssertionError("third lookup should exceed maxOfferingCalls")


def test_offering_lookup_respects_tool_policy_cap() -> None:
    tracker = BudgetTracker(Budget(max_offering_calls=9))
    tracker.record_offering_call({"listOfferings": 1})
    try:
        tracker.record_offering_call({"listOfferings": 1})
    except BudgetExceeded as exc:
        assert "listOfferings" in str(exc)
    else:
        raise AssertionError("tool_policy cap of 1 should refuse the second lookup")
