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
REVIEW = "REVIEW"

#: fixture 没写 outcome 时的取值。按未知处理：缺成绩不能当成已通过（AGENTS.md「unknown 不能通过」）。
MISSING_OUTCOME_DEFAULT = "UNKNOWN"

OUTCOMES = ("PASSED", "FAILED", "IN_PROGRESS", "UNKNOWN")


class UnsupportedCase(Exception):
    """用例无法按契约构造请求：不是失败，是没有有效结果。"""


@dataclass
class Step:
    """一次请求。body / params 可以是固定对象，也可以是拿前面响应算出来的函数。"""

    label: str
    path: str
    body: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]] | None = None
    note: str = ""
    method: str = "POST"
    params: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]] | None = None


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


CONSTRAINT_KEYS = ("kind", "courseCode", "teacherKey", "dayOfWeek", "section", "value", "sourceText")
SOFT_KEYS = ("dimension", "value", "sourceText")
PAIR_KEYS = ("courseCode", "teacherKey", "mode")


def _normalize_items(items: list[Any], allowed: tuple[str, ...], label: str, notes: list[str]) -> list[dict[str, Any]]:
    """把 fixture 里的条目按契约字段白名单裁一遍：缺的可空字段补 None，多的字段丢掉并留痕。"""
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise UnsupportedCase(f"{label} 里有非结构化条目 {item!r}")
        dropped = sorted(set(item) - set(allowed))
        if dropped:
            notes.append(f"{label} 丢弃契约外字段 {dropped}（原句仍在 sourceText 里）")
        row = {key: item.get(key) for key in allowed}
        out.append(row)
    return out


def _normalize_intent(intent: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    """fixture 的 intent 未必符合契约形状：按白名单裁，缺的可空字段补 None。"""
    body = dict(_empty_intent())
    for key in ("motives", "priorityOrder", "interestTags", "careerDirectionIds"):
        if isinstance(intent.get(key), list):
            body[key] = intent[key]
    if isinstance(intent.get("hardConstraints"), list):
        body["hardConstraints"] = _normalize_items(intent["hardConstraints"], CONSTRAINT_KEYS, "hardConstraints", notes)
    if isinstance(intent.get("softPreferences"), list):
        body["softPreferences"] = _normalize_items(intent["softPreferences"], SOFT_KEYS, "softPreferences", notes)
    if isinstance(intent.get("pinnedTeacherCoursePairs"), list):
        body["pinnedTeacherCoursePairs"] = _normalize_items(
            intent["pinnedTeacherCoursePairs"], PAIR_KEYS, "pinnedTeacherCoursePairs", notes
        )
    extra = sorted(set(intent) - set(body))
    if extra:
        notes.append(f"intent 里丢弃契约外字段 {extra}")
    return body


def _constraints_from_desired(courses: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """把「想选的课」折成 PIN_COURSE 约束。

    培养方案原表用波浪号表示两个编号合上一门课（08305009~010），契约标识符字符集不含波浪号。
    本模块的口径是取波浪号之前的主号作为课程标识，原写法原样保留在 sourceText；
    不做字符替换，也不在系统里造一个原表里不存在的编号。
    """
    constraints: list[dict[str, Any]] = []
    notes: list[str] = []
    for course in courses:
        if not isinstance(course, dict):
            raise UnsupportedCase(f"desiredCourses 里有非结构化条目 {course!r}：无法确定课程编号，不猜测")
        original = course.get("courseCode")
        code = original
        if not _id_ok(code):
            main = str(original).split("~")[0].strip() if isinstance(original, str) and "~" in original else None
            if not _id_ok(main):
                # 单元格引用（如「计科学1-A12」）不是课程标识符：不猜，也不丢课名，留给题面自由文本
                notes.append(
                    f"编号 {original!r} 不是契约标识符，也不是合上编号：该课不折成 PIN_COURSE，"
                    f"课名「{course.get('courseName') or ''}」保留在题面里由 Runner 解析"
                )
                continue
            code = main
            notes.append(f"编号 {original} 含波浪号：取主号 {code} 作为课程标识，原写法保留在 sourceText")
        source_text = course.get("courseName") or code
        if code != original:
            source_text = f"{source_text}（原表编号 {original}）"
        constraints.append(
            {
                "kind": "PIN_COURSE",
                "courseCode": code,
                "teacherKey": None,
                "dayOfWeek": None,
                "section": None,
                "value": None,
                "sourceText": source_text,
            }
        )
    return constraints, notes


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
        body_intent = _normalize_intent(intent, notes)
        notes.append("intent 取 fixture 的 intent 字段并按契约白名单规整（题面输入）")
    elif isinstance(fixture.get("desiredCourses"), list):
        body_intent = dict(_empty_intent())
        body_intent["motives"] = ["SCHEDULE"]
        constraints, constraint_notes = _constraints_from_desired(fixture["desiredCourses"])
        body_intent["hardConstraints"] = constraints
        notes.append("intent 由 fixture.desiredCourses 派生：每门课记为 PIN_COURSE（题面输入）")
        notes.extend(constraint_notes)
    else:
        body_intent = _empty_intent()
        notes.append("fixture 没有结构化 intent：intent 留空，由 Runner 自己澄清（题面只有自由文本）")

    record_id = academic_record_id or fixture.get("academicRecordId")
    if _id_ok(record_id):
        notes.append("academicRecordId 取 fixture 字段")
    else:
        record_id = None
        notes.append("fixture 没有合法 academicRecordId：不伪造已修记录，由适配层先落一条空记录")

    if "originalGoal" in fixture or "newGoal" in fixture:
        notes.append("replan 题面：previousPlanId 只能引用服务端已有方案，本用例没有可引用的 id，按新目标重算")

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
        if not isinstance(course, dict):
            raise UnsupportedCase(f"completedCourses 里有非结构化条目 {course!r}：无法确定课程编号，不猜测")
        code = course.get("courseCode")
        if not _id_ok(code):
            # 学生只给了课名与成绩、没给课号（G4-005 这类跨专业咨询）：不猜课号，这条不入库
            notes.append(f"已修课程「{course.get('courseName') or '未命名'}」没有合法课号，未提交到记录里（不猜编号）")
            continue
        outcome = course.get("outcome")
        if outcome is None:
            outcome = missing_outcome
            filled_outcome += 1
        elif outcome not in OUTCOMES:
            raise UnsupportedCase(f"outcome {outcome!r} 不在契约枚举内")
        term = course.get("completedTerm")
        if term is not None and not _id_ok(term):
            raise UnsupportedCase(f"completedTerm {term!r} 不符合契约 Id 字符集")
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
            f"{filled_outcome} 门已修课程 fixture 未写 outcome，按 {missing_outcome} 处理（缺成绩不当作已通过；应在 fixture 补字段）"
        )
    if any("completedTerm" in course for course in fixture.get("completedCourses") or []):
        notes.append("completedTerm 取 fixture 字段；fixture 没写就不传（契约允许 null，不自行编学期编号）")
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


def upstream_dependent(fixture: dict[str, Any]) -> bool:
    """题面是否依赖上游解析快照（班次容量、采集时间这类只存在于快照里的事实）。"""
    return isinstance(fixture.get("offering"), dict)


def _upstream_notes(fixture: dict[str, Any]) -> list[str]:
    if not upstream_dependent(fixture):
        return []
    return [
        (
            "依赖上游：容量与采集时间只存在于 offering 快照里，契约的 PlanningRequest 没有承载字段，"
            "没有 Java/数据集解析时这条判据记为依赖上游"
        )
    ]


def classify(case: dict[str, Any], fixture: dict[str, Any]) -> tuple[str, str]:
    """判定该题面该打哪条路，并给出依据（判定依据要能被人复核）。"""
    if isinstance(fixture.get("intent"), dict):
        return PLANNING, "fixture 带结构化 intent，属规划类题面"
    if isinstance(fixture.get("desiredCourses"), list):
        return PLANNING, "fixture 带待选课程清单，属规划类题面"
    if "originalGoal" in fixture or "newGoal" in fixture:
        return PLANNING, "replan 题面：只给目标变更与原方案摘要，没有可引用的 previousPlanId"
    if isinstance(fixture.get("completed"), dict) or "reportedCredits" in fixture:
        return AUDIT, "fixture 给的是学生自报的各类别学分汇总，没有逐门记录，按缺失明细处理"
    if "completedCourses" in fixture or "academicRecordId" in fixture:
        return AUDIT, "fixture 带已修记录（或明确说明没有），题面问的是培养要求缺口"
    if "reviewNotes" in fixture or "reviewSource" in fixture:
        return REVIEW, "题面问某位老师的授课与给分，走评价检索端点"
    if "queriedCourse" in fixture:
        return CATALOG, "题面问某门课能否计入某类，需要目录检索端点，本轮未接"
    if isinstance(fixture.get("offering"), dict) or isinstance(fixture.get("studentReported"), dict):
        return PLANNING, "fixture 带班次与自报人数，题面问的是能否选上，按规划类题面处理（容量事实由快照提供）"
    if isinstance(fixture.get("uploadedSnapshot"), dict):
        return PLANNING, "fixture 只有学生上传件与自由文本，intent 留空由 Runner 澄清"
    raise UnsupportedCase(f"fixture 形态无法归入规划类或核查类（含键：{', '.join(sorted(fixture))}）")


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
    if route == REVIEW:
        codes = [
            note.get("courseCode")
            for note in fixture.get("reviewNotes") or []
            if isinstance(note, dict) and _id_ok(note.get("courseCode"))
        ]
        if not codes:
            raise UnsupportedCase("评价检索接口要求 courseCode，fixture 里没有可用的课程号")
        plan.notes = [
            reason,
            f"评价检索按课程号 {codes[0]} 查询（接口 courseCode 必填，教师名不进请求）",
            "修读学期在 fixture 里为 null：应如实说未知，不得当作本学期事实",
        ]
        plan.steps = [
            Step("评价检索", "/api/v1/reviews/search", method="GET", params={"courseCode": codes[0], "limit": 10})
        ]
        return plan
    if route == PLANNING:
        body, notes = planning_body(case, fixture, mode=mode)
        plan.notes = notes
        if body.get("academicRecordId"):
            plan.notes = [*notes, *_upstream_notes(fixture)]
            plan.steps = [Step("规划请求", "/api/v1/planning", body)]
            return plan
        plan.notes = [*notes, "先落一条空记录（transcriptComplete=false）拿 id，再发规划请求"]
        plan.notes += _upstream_notes(fixture)
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
