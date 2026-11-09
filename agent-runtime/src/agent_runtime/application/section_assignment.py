"""Deterministic section (class) choice for planned courses (module C).

Java stays the only authority on conflicts and constraints: ``validatePlan``
returns the verdict. This module only picks one section per course from the
structured meetings that Java returned on ``listOfferings``, so the candidate
plan handed to Java is conflict-free on those meetings. It never parses
``meetingTextRaw`` and never reads credit rules.

Ordering of preferences, from the student's side:
  1. a MUST teacher pin (hard filter), a PREFER teacher pin (ordering only);
  2. avoided time slots from the hard constraints (hard filter) and the soft
     ``schedule.blocked_*`` preferences (ordering only);
  3. more review evidence for the section's teacher;
  4. ``classId`` order, so the result is stable.

Sections whose time is not PARSED are never chosen automatically. A course
whose only sections are unparsed gets no class, with a reason, because the
plan must not claim those sections are conflict-free.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from agent_runtime.api.schemas import Constraint, CourseOffering, Meeting, SoftPreference

# Upper bound on search nodes. Past it the best assignment found so far is used,
# which is never worse than the greedy seed. Keeps a worst case bounded.
NODE_LIMIT = 20000

REASON_NO_OFFERING = "本学期没有开设这门课"
REASON_TEACHER_NO_OFFERING = "所选教师在本开课快照中没有该课程的班次"
REASON_UNPARSED = "班次时间未解析，无法判断冲突，未自动选定班次"
REASON_BLOCKED = "可选班次都与学生设定的必避时段冲突"
REASON_CONFLICT = "与其他推荐课程的时间冲突，无法在同一课表中同时安排"
_WEEKDAY_NAMES = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
REASON_BUDGET = "本次班次查询次数已达上限，未选定班次"
REASON_LOOKUP_FAILED = "班次查询失败，未选定班次"

_SLOT_VALUE = re.compile(r"^([1-7])-([1-9][0-9]?)$")
_DAY_VALUE = re.compile(r"^[1-7]$")
_SECTION_VALUE = re.compile(r"^[1-9][0-9]?$")


@dataclass(frozen=True)
class SlotBlock:
    """An avoided time: a weekday, a section number, or one weekday-section pair."""

    dayOfWeek: int | None
    section: int | None

    def hits(self, meeting: Meeting) -> bool:
        if self.dayOfWeek is not None and meeting.dayOfWeek != self.dayOfWeek:
            return False
        if self.section is not None and not (
            meeting.sectionStart <= self.section <= meeting.sectionEnd
        ):
            return False
        return True


def hard_blocks(constraints: Iterable[Constraint]) -> tuple[SlotBlock, ...]:
    """BLOCK_DAY / BLOCK_SECTION / BLOCK_SLOT as avoided times. Other kinds are ignored."""
    blocks: list[SlotBlock] = []
    for constraint in constraints:
        if constraint.kind == "BLOCK_DAY" and constraint.dayOfWeek is not None:
            blocks.append(SlotBlock(constraint.dayOfWeek, None))
        elif constraint.kind == "BLOCK_SECTION" and constraint.section is not None:
            blocks.append(SlotBlock(None, constraint.section))
        elif (
            constraint.kind == "BLOCK_SLOT"
            and constraint.dayOfWeek is not None
            and constraint.section is not None
        ):
            blocks.append(SlotBlock(constraint.dayOfWeek, constraint.section))
    return tuple(blocks)


def soft_blocks(preferences: Iterable[SoftPreference]) -> tuple[SlotBlock, ...]:
    """schedule.blocked_day / blocked_section / blocked_slot, as used by the web form.

    Values that do not match the expected shape are dropped, not guessed: a soft
    preference only changes ordering, so dropping it is the safe failure.
    """
    blocks: list[SlotBlock] = []
    for preference in preferences:
        value = preference.value.strip()
        if preference.dimension == "schedule.blocked_day" and _DAY_VALUE.match(value):
            blocks.append(SlotBlock(int(value), None))
        elif preference.dimension == "schedule.blocked_section" and _SECTION_VALUE.match(value):
            blocks.append(SlotBlock(None, int(value)))
        elif preference.dimension == "schedule.blocked_slot":
            match = _SLOT_VALUE.match(value)
            if match:
                blocks.append(SlotBlock(int(match.group(1)), int(match.group(2))))
    return tuple(blocks)


def describe_block(block: SlotBlock) -> str:
    """Human text for an avoided time, e.g. 周一整天, 每周第2节 or 周三第1节."""
    if block.dayOfWeek is not None and block.section is not None:
        return f"{_WEEKDAY_NAMES[block.dayOfWeek]}第{block.section}节"
    if block.dayOfWeek is not None:
        return f"{_WEEKDAY_NAMES[block.dayOfWeek]}整天"
    return f"每周第{block.section}节"


def describe_meeting(meeting: Meeting) -> str:
    day = _WEEKDAY_NAMES[meeting.dayOfWeek]
    if meeting.sectionStart == meeting.sectionEnd:
        return f"{day}第{meeting.sectionStart}节"
    return f"{day}第{meeting.sectionStart}-{meeting.sectionEnd}节"


def _blocked_reason(parsed: Sequence[CourseOffering], blocks: Sequence[SlotBlock]) -> str:
    """REASON_BLOCKED, naming the avoided times that actually hit the parsed sections."""
    hit: list[SlotBlock] = []
    for block in blocks:
        if block in hit:
            continue
        if any(block.hits(meeting) for offering in parsed for meeting in offering.meetings):
            hit.append(block)
    return f"{REASON_BLOCKED}：" + "、".join(describe_block(block) for block in hit)


@dataclass(frozen=True)
class SectionOption:
    class_id: str
    course_code: str
    teacher_key: str | None
    meetings: tuple[Meeting, ...]
    soft_hits: int
    review_count: int


@dataclass(frozen=True)
class CourseNeed:
    """What the plan item and the student's pins require for one course."""

    course_code: str
    item_teacher_key: str | None
    must_teacher_key: str | None
    prefer_teacher_key: str | None


@dataclass(frozen=True)
class CourseOptions:
    options: tuple[SectionOption, ...]
    reason: str | None  # set when there are no options; None when options exist


# TODO(java-conflict): this interval-overlap test is a Python copy of a conflict
# rule. The contract (contracts/java.openapi.json) has no endpoint that decides
# conflicts for a candidate set: validatePlan judges one fully chosen plan, and
# calling it per search node would exceed the validation budget (2 calls). Until
# Java exposes such an endpoint, this stays a selection aid only. Java's
# validatePlan on the final plan remains the authority, and the runner always
# runs it after assignment. Do not treat a True/False here as a verdict.
def _meetings_overlap(first: Meeting, second: Meeting) -> bool:
    return (
        first.dayOfWeek == second.dayOfWeek
        and first.sectionStart <= second.sectionEnd
        and second.sectionStart <= first.sectionEnd
        and bool(set(first.weeks) & set(second.weeks))
    )


def sections_conflict(first: SectionOption, second: SectionOption) -> bool:
    """True when two sections share a weekday, overlapping sections and a common week.

    This is only a selection aid on Java's structured meetings. Java's validatePlan
    still decides the final verdict for the chosen plan. See the TODO above.
    """
    return any(_meetings_overlap(a, b) for a in first.meetings for b in second.meetings)


def course_options(
    need: CourseNeed,
    offerings: Sequence[CourseOffering],
    blocks: Sequence[SlotBlock],
    soft: Sequence[SlotBlock],
    review_counts: Mapping[str | None, int],
) -> CourseOptions:
    """Eligible sections for one course, best first. Empty options carry the reason."""
    own = [offering for offering in offerings if offering.courseCode == need.course_code]
    if not own:
        return CourseOptions((), REASON_NO_OFFERING)

    wanted = need.must_teacher_key or need.item_teacher_key
    if wanted is not None:
        own = [offering for offering in own if offering.teacherKey == wanted]
        if not own:
            return CourseOptions((), REASON_TEACHER_NO_OFFERING)

    parsed = [offering for offering in own if offering.parseStatus == "PARSED"]
    if not parsed:
        return CourseOptions((), REASON_UNPARSED)

    free = [
        offering
        for offering in parsed
        if not any(block.hits(meeting) for meeting in offering.meetings for block in blocks)
    ]
    if not free:
        return CourseOptions((), _blocked_reason(parsed, blocks))

    seen: set[str] = set()
    options: list[SectionOption] = []
    for offering in free:
        if offering.classId in seen:
            continue
        seen.add(offering.classId)
        soft_hits = sum(
            1 for meeting in offering.meetings if any(block.hits(meeting) for block in soft)
        )
        options.append(
            SectionOption(
                class_id=offering.classId,
                course_code=need.course_code,
                teacher_key=offering.teacherKey,
                meetings=tuple(offering.meetings),
                soft_hits=soft_hits,
                review_count=review_counts.get(offering.teacherKey, 0),
            )
        )

    prefer = need.prefer_teacher_key if wanted is None else None

    def order(option: SectionOption) -> tuple[int, int, int, str]:
        not_preferred = 0 if prefer is None or option.teacher_key == prefer else 1
        return (not_preferred, option.soft_hits, -option.review_count, option.class_id)

    options.sort(key=order)
    return CourseOptions(tuple(options), None)


def conflict_names(
    options: Sequence[SectionOption],
    placed: Sequence[tuple[SectionOption, str]],
) -> list[str]:
    """Name the placed sections that clash with any of this course's options.

    ``placed`` pairs each chosen section with its course label (for example
    "人工智能（08306029）"). Each clash reads "与 <label><weekday and sections>冲突",
    using the placed section's own meeting. Empty when nothing clashes by name.
    """
    named: list[str] = []
    for pick, label in placed:
        clash = next(
            (
                meeting
                for meeting in pick.meetings
                for option in options
                if any(_meetings_overlap(meeting, other) for other in option.meetings)
            ),
            None,
        )
        if clash is None:
            continue
        text = f"与 {label}{describe_meeting(clash)}冲突"
        if text not in named:
            named.append(text)
    return named


def choose_sections(
    slots: Sequence[Sequence[SectionOption]],
    *,
    node_limit: int = NODE_LIMIT,
) -> list[SectionOption | None]:
    """Pick at most one section per slot so that the most slots get a section.

    ``slots`` is ordered by priority: earlier slots win ties. The result is the
    first maximal assignment in preference order, so when every slot can be
    placed the answer is the preference-first conflict-free combination. A slot
    left as None is one that cannot be placed alongside the others.
    """
    count = len(slots)
    greedy: list[SectionOption | None] = []
    picked: list[SectionOption] = []
    for options in slots:
        pick = next((o for o in options if not any(sections_conflict(o, p) for p in picked)), None)
        greedy.append(pick)
        if pick is not None:
            picked.append(pick)

    best: list[SectionOption | None] = list(greedy)
    best_count = sum(1 for pick in greedy if pick is not None)
    if best_count == count:
        return best

    current: list[SectionOption | None] = [None] * count
    chosen: list[SectionOption] = []
    nodes = 0

    def search(index: int, placed: int) -> None:
        nonlocal best, best_count, nodes
        nodes += 1
        if nodes > node_limit or best_count == count:
            return
        if placed + (count - index) <= best_count:
            return
        if index == count:
            best_count = placed
            best = list(current)
            return
        for option in slots[index]:
            if any(sections_conflict(option, other) for other in chosen):
                continue
            current[index] = option
            chosen.append(option)
            search(index + 1, placed + 1)
            chosen.pop()
            current[index] = None
            if best_count == count or nodes > node_limit:
                return
        search(index + 1, placed)

    search(0, 0)
    return best
