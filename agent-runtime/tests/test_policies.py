from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_runtime.api.schemas import (
    Constraint,
    GoalIntent,
    Issue,
    PlanItem,
    PlanningRequest,
    PlanValidation,
    TeacherPreference,
)
from agent_runtime.domain.policies.answer_compiler import AnswerCompiler
from agent_runtime.domain.policies.candidate_guard import CandidateGuard, KnownFacts
from agent_runtime.domain.policies.clarification_policy import ClarificationPolicy
from agent_runtime.domain.policies.intent_resolver import IntentResolver


def _request_with_intent(intent: GoalIntent) -> PlanningRequest:
    return PlanningRequest(
        schemaVersion="1.0",
        curriculumSnapshotId="curr:x",
        offeringSnapshotId=None,
        academicRecordId="record:x",
        mode="REAL",
        promptText="",
        intent=intent,
        previousPlanId=None,
    )


def _empty_intent() -> GoalIntent:
    return GoalIntent(
        motives=[],
        priorityOrder=[],
        hardConstraints=[],
        softPreferences=[],
        pinnedTeacherCoursePairs=[],
        interestTags=[],
        careerDirectionIds=[],
    )


def test_candidate_guard_rejects_unknown_ids() -> None:
    guard = CandidateGuard()
    facts = KnownFacts(
        course_codes=frozenset({"CS101"}),
        teacher_keys=frozenset({"t1"}),
        class_ids=frozenset({"c1"}),
    )
    items = [
        PlanItem(courseCode="CS999", teacherKey="t1", classId="c1"),
        PlanItem(courseCode="CS101", teacherKey="t2", classId="c1"),
        PlanItem(courseCode="CS101", teacherKey="t1", classId="c9"),
    ]
    issues = guard.check(items, facts)
    assert [issue.code for issue in issues] == [
        "UNKNOWN_COURSE",
        "UNKNOWN_TEACHER",
        "UNKNOWN_CLASS",
    ]


def test_answer_compiler_preserves_verdict() -> None:
    verdict = PlanValidation(
        verifierResultId="verify:x",
        verdict="UNKNOWN",
        scope="COURSE_ONLY",
        curriculumSnapshotId="curr:x",
        offeringSnapshotId=None,
        recordRevision=1,
        violations=[],
        unknownChecks=[
            Issue(
                code="OFFERING_UNAVAILABLE",
                message="未取得本学期班次",
                field="offeringSnapshotId",
                retryable=False,
            )
        ],
        performedChecks=["COURSE_EXISTS"],
        sourceRefIds=["source:x"],
    )
    recommendation = AnswerCompiler().recommend(
        plan_id="plan:x",
        items=[PlanItem(courseCode="CS101", teacherKey=None, classId=None)],
        explanation="仅课程层建议",
        review_note_ids=[],
        verdict=verdict,
    )
    assert recommendation.verification == verdict
    assert recommendation.verification.verdict == "UNKNOWN"


def test_intent_resolver_requires_goal() -> None:
    resolved = IntentResolver().resolve(_request_with_intent(_empty_intent()))
    assert resolved.needs_clarification is True
    assert "motives" in resolved.missing


def test_intent_resolver_accepts_goal() -> None:
    intent = _empty_intent()
    intent.motives = ["GPA"]
    intent.priorityOrder = ["GPA"]
    resolved = IntentResolver().resolve(_request_with_intent(intent))
    assert resolved.needs_clarification is False


def test_intent_resolver_asks_when_must_teacher_and_hard_time_unranked() -> None:
    intent = _empty_intent()
    intent.motives = ["SPECIFIC_TEACHER", "SCHEDULE"]
    intent.priorityOrder = ["GPA"]
    intent.pinnedTeacherCoursePairs = [
        TeacherPreference(courseCode="CS101", teacherKey="teacher:demo", mode="MUST")
    ]
    intent.hardConstraints = [
        Constraint(
            kind="BLOCK_SLOT",
            courseCode=None,
            teacherKey=None,
            dayOfWeek=5,
            section=1,
            value=None,
            sourceText="周五第1节必须空",
        )
    ]
    resolved = IntentResolver().resolve(_request_with_intent(intent))
    assert resolved.needs_clarification is True
    assert "teacher_vs_schedule" in resolved.missing
    question = ClarificationPolicy().build_question(resolved)
    assert question.questionId == "tradeoff:teacher-vs-schedule"
    assert {choice.value for choice in question.choices} == {"KEEP_TEACHER", "KEEP_SCHEDULE"}


def test_intent_resolver_skips_tradeoff_when_both_are_ranked() -> None:
    intent = _empty_intent()
    intent.motives = ["SPECIFIC_TEACHER", "SCHEDULE"]
    intent.priorityOrder = ["SPECIFIC_TEACHER", "SCHEDULE"]
    intent.pinnedTeacherCoursePairs = [
        TeacherPreference(courseCode="CS101", teacherKey="teacher:demo", mode="MUST")
    ]
    intent.hardConstraints = [
        Constraint(
            kind="BLOCK_DAY",
            courseCode=None,
            teacherKey=None,
            dayOfWeek=5,
            section=None,
            value=None,
            sourceText="周五没课",
        )
    ]
    resolved = IntentResolver().resolve(_request_with_intent(intent))
    assert resolved.needs_clarification is False


def _constraint(**overrides: object) -> dict:
    base: dict[str, object] = {
        "kind": "BLOCK_DAY",
        "courseCode": None,
        "teacherKey": None,
        "dayOfWeek": 1,
        "section": None,
        "value": None,
        "sourceText": "周五没课",
    }
    base.update(overrides)
    return base


def test_constraint_block_day_rejects_section() -> None:
    with pytest.raises(ValidationError):
        Constraint(**_constraint(kind="BLOCK_DAY", dayOfWeek=1, section=2))


def test_constraint_block_section_rejects_day() -> None:
    with pytest.raises(ValidationError):
        Constraint(**_constraint(kind="BLOCK_SECTION", dayOfWeek=1, section=3))


def test_constraint_block_slot_requires_both() -> None:
    with pytest.raises(ValidationError):
        Constraint(**_constraint(kind="BLOCK_SLOT", dayOfWeek=1, section=None))


def test_constraint_block_slot_accepts_both() -> None:
    constraint = Constraint(**_constraint(kind="BLOCK_SLOT", dayOfWeek=1, section=3))
    assert constraint.dayOfWeek == 1
    assert constraint.section == 3
