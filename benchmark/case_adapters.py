"""把题面与 fixture 折成「要打哪些端点、每步请求体是什么」。

为什么要单独一层
  同一个 case set 里的题面问的不是同一件事：有的问「怎么排」，有的问「我够不够毕业」，
  有的问「这个班次我选得上吗」。用一次 /planning 硬套会把后两类判成构造失败，
  于是骨架里出现 7 例 BLOCKED，看起来像 Runner 不行，其实是适配层没做。

规则
  * 只做「题面输入 → 契约请求体」的折算，不产生任何答案内容；
  * 折算不出来的如实抛 UnsupportedCase，不换字段绕过去、不编造编号；
  * 每处折算都写进 notes，跟着逐例记录一起落盘，复核时能看到。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")

PLANNING = "PLANNING"
AUDIT = "AUDIT"
CATALOG = "CATALOG"

#: fixture 没写 outcome 时的折算值。写进 notes，别让它变成看不见的假设。
MISSING_OUTCOME_DEFAULT = "PASSED"

OUTCOMES = ("PASSED", "FAILED", "IN_PROGRESS", "UNKNOWN")


class UnsupportedCase(Exception):
    """用例无法按契约构造请求：不是失败，是没有有效结果。"""


@dataclass
class Step:
    """一次请求。body 可以是固定对象，也可以是拿前面响应算出来的函数。"""

    label: str
    path: str
    body: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]
    note: str = ""


@dataclass
class CasePlan:
    case_id: str
    group_id: str
    route: str
    reason: str
    steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _id_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_PATTERN.fullmatch(value))


def _empty_intent() -> dict[str, Any]:
    return {
        "motives": [],
        "priorityOrder": [],
        "hardConstraints": [],
        "softPreferences": [],
        "pinnedTeacherCoursePairs": [],
        "interestTags": [],
        "careerDirectionIds": [],
    }


def _constraints_from_desired(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for course in courses:
        code = course.get("courseCode")
        if not _id_ok(code):
            raise UnsupportedCase(f"fixture 的 courseCode {code!r} 不符合契约 Id 字符集，无法构造 PIN_COURSE 约束")
        constraints.append(
            {
                "kind": "PIN_COURSE",
                "courseCode": code,
                "teacherKey": None,
                "dayOfWeek": None,
                "section": None,
                "value": None,
                "sourceText": course.get("courseName") or code,
            }
        )
    return constraints


def planning_body(
    case: dict[str, Any],
    fixture: dict[str, Any],
    *,
    academic_record_id: str | None = None,
    mode: str = "SIMULATION",
) -> tuple[dict[str, Any], list[str]]:
    """折 PlanningRequest。返回 (请求体, 备注)。"""
    notes: list[str] = []
    intent = fixture.get("intent")
    if isinstance(intent, dict):
        body_intent = intent
        notes.append("intent 取 fixture 的 intent 字段（题面输入）")
    elif isinstance(fixture.get("desiredCourses"), list):
        body_intent = dict(_empty_intent())
        body_intent["motives"] = ["SCHEDULE"]
        body_intent["hardConstraints"] = _constraints_from_desired(fixture["desiredCourses"])
        notes.append("intent 由 fixture.desiredCourses 派生：每门课记为 PIN_COURSE（题面输入）")
    else:
        body_intent = _empty_intent()
        notes.append("fixture 没有结构化 intent：intent 留空，由 Runner 自己澄清（题面只有自由文本）")

    record_id = academic_record_id or fixture.get("academicRecordId")
    if _id_ok(record_id):
        notes.append("academicRecordId 取 fixture 字段")
    else:
        record_id = None
        notes.append("fixture 没有合法 academicRecordId：不伪造已修记录，由适配层先落一条空记录")

    prompt = fixture.get("promptText") or case.get("userQuery") or ""
    body = {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": case.get("curriculumSnapshotId"),
        "offeringSnapshotId": case.get("offeringSnapshotId") or fixture.get("offeringSnapshotId"),
        "academicRecordId": record_id,
        "mode": mode,
        "promptText": prompt,
        "intent": body_intent,
        "previousPlanId": None,
    }
    return body, notes


def record_body(
    case: dict[str, Any],
    fixture: dict[str, Any],
    *,
    missing_outcome: str = MISSING_OUTCOME_DEFAULT,
) -> tuple[dict[str, Any], list[str]]:
    """折 AcademicRecordInput：把 fixture 的已修课程列表送进 academic-records。

    契约的 CompletedCourse 只要四个字段，fixture 里 courseName / category / termIndex
    没有对应字段，传不过去；outcome 与 completedTerm 则要折或补。
    """
    if missing_outcome not in OUTCOMES:
        raise UnsupportedCase(f"missing_outcome 只能是 {OUTCOMES} 之一，收到 {missing_outcome!r}")
    notes: list[str] = []
    courses: list[dict[str, Any]] = []
    filled_outcome = 0
    for course in fixture.get("completedCourses") or []:
        code = course.get("courseCode")
        if not _id_ok(code):
            raise UnsupportedCase(f"已修课程的 courseCode {code!r} 不符合契约 Id 字符集")
        outcome = course.get("outcome")
        if outcome is None:
            outcome = missing_outcome
            filled_outcome += 1
        elif outcome not in OUTCOMES:
            raise UnsupportedCase(f"outcome {outcome!r} 不在契约枚举内")
        term = course.get("completedTerm")
        if term is None and isinstance(course.get("termIndex"), int):
            term = f"term-{course['termIndex']}"
        if term is not None and not _id_ok(term):
            term = None
        courses.append(
            {
                "courseCode": code,
                "earnedCredits": course.get("credits"),
                "outcome": outcome,
                "completedTerm": term,
            }
        )
    if filled_outcome:
        notes.append(
            f"{filled_outcome} 门已修课程 fixture 未写 outcome，按 {missing_outcome} 折算（折算假设，待编写人确认）"
        )
    if fixture.get("termIndex") is not None:
        notes.append("completedTerm 由 fixture.termIndex 折成 term-<n>")
    unsent = [
        key for key in ("englishTaughtCourse", "overseasExchangeCredits", "majorId", "studentTerm") if key in fixture
    ]
    if unsent:
        notes.append(f"fixture 里 {', '.join(unsent)} 在契约 AcademicRecordInput 没有对应字段，未传")
    body = {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": case.get("curriculumSnapshotId"),
        "completedCourses": courses,
        "transcriptComplete": bool(fixture.get("transcriptComplete", True)),
        "sourceKind": "SYNTHETIC",
    }
    return body, notes


def empty_record_body(case: dict[str, Any]) -> dict[str, Any]:
    """缺已修记录时的空记录：transcriptComplete=false，不塞任何课程。

    契约 PlanningRequest.academicRecordId 必填且不可为 null，所以「学生还没导入记录」
    只能先落一条明确的空记录拿 id，不能拿占位字符串冒充。
    """
    return {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": case.get("curriculumSnapshotId"),
        "completedCourses": [],
        "transcriptComplete": False,
        "sourceKind": "SYNTHETIC",
    }


def classify(case: dict[str, Any], fixture: dict[str, Any]) -> tuple[str, str]:
    """判定该题面该打哪条路，并给出依据（判定依据要能被人复核）。"""
    if isinstance(fixture.get("intent"), dict):
        return PLANNING, "fixture 带结构化 intent，属规划类题面"
    if isinstance(fixture.get("desiredCourses"), list):
        return PLANNING, "fixture 带待选课程清单，属规划类题面"
    if "completedCourses" in fixture or "academicRecordId" in fixture:
        return AUDIT, "fixture 带已修记录（或明确说明没有），题面问的是培养要求缺口"
    if "queriedCourse" in fixture:
        return CATALOG, "题面问某门课能否计入某类，需要目录检索端点，本轮未接"
    if isinstance(fixture.get("offering"), dict) or isinstance(fixture.get("studentReported"), dict):
        return PLANNING, "fixture 带班次与自报人数，题面问的是能否选上，按规划类题面处理（容量事实由快照提供）"
    if isinstance(fixture.get("uploadedSnapshot"), dict):
        return PLANNING, "fixture 只有学生上传件与自由文本，intent 留空由 Runner 澄清"
    raise UnsupportedCase("fixture 形态无法归入规划类或核查类")


def build_plan(
    case: dict[str, Any],
    fixture: dict[str, Any],
    *,
    mode: str = "SIMULATION",
    missing_outcome: str = MISSING_OUTCOME_DEFAULT,
) -> CasePlan:
    route, reason = classify(case, fixture)
    plan = CasePlan(
        case_id=str(case.get("caseId") or "unknown"),
        group_id=str(case.get("groupId") or "unknown"),
        route=route,
        reason=reason,
    )
    if route == CATALOG:
        plan.notes = [reason]
        return plan
    if route == PLANNING:
        body, notes = planning_body(case, fixture, mode=mode)
        plan.notes = notes
        if body.get("academicRecordId"):
            plan.steps = [Step("规划请求", "/api/v1/planning", body)]
            return plan
        plan.notes = [*notes, "先落一条空记录（transcriptComplete=false）拿 id，再发规划请求"]
        plan.steps = [
            Step("落空记录", "/api/v1/academic-records", empty_record_body(case)),
            Step(
                "规划请求",
                "/api/v1/planning",
                lambda saved: {**body, "academicRecordId": (saved.get("data") or {}).get("academicRecordId")},
            ),
        ]
        return plan

    body, notes = record_body(case, fixture, missing_outcome=missing_outcome)
    plan.notes = notes
    plan.steps = [
        Step("落已修记录", "/api/v1/academic-records", body),
        Step(
            "培养要求核查",
            "/api/v1/requirements/audit",
            lambda saved: {
                "schemaVersion": "1.0",
                "curriculumSnapshotId": case.get("curriculumSnapshotId"),
                "academicRecordId": (saved.get("data") or {}).get("academicRecordId"),
            },
        ),
    ]
    return plan
