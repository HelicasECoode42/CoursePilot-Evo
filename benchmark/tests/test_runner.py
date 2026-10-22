"""D-F2 骨架自测：钉住「请求怎么构造、判定怎么分级、成本缺失怎么记、汇总怎么等权」。

不测语义（那是模型和 Runner 的事），也不连真实服务：传输层用假对象。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from runner import (
    BLOCKED,
    DEGRADED,
    FAIL,
    PASS,
    BenchmarkRunner,
    UnsupportedCase,
    answer_text,
    load_manifest_schema,
    planning_body,
    validate_manifest,
)

MANIFEST = {
    "schemaVersion": "1.0",
    "runId": "test-run",
    "benchmarkSetVersion": "set-v1",
    "evaluatorVersion": "scorer-v0",
    "curriculumSnapshotId": "3c405feaa6d7",
    "offeringSnapshotId": None,
    "javaToolApiVersion": "unset",
    "verifierVersion": "unset",
    "harnessVersion": "w2",
    "parentVersion": None,
    "modelId": "unset-placeholder",
    "temperature": 0.0,
    "maxInputTokens": 8000,
    "maxOutputTokens": 2000,
    "maxToolCalls": 6,
    "maxModelCalls": 3,
    "deadlineMs": 45000,
    "repeatCount": 1,
    "seed": 0,
    "createdAt": "2026-10-21T00:00:00Z",
}

INTENT = {
    "motives": ["SCHEDULE"],
    "priorityOrder": [],
    "hardConstraints": [],
    "softPreferences": [],
    "pinnedTeacherCoursePairs": [],
    "interestTags": [],
    "careerDirectionIds": [],
}

GOLD = {
    "caseId": "G2-001",
    "requiredFacts": ["不要早八"],
    "requiredUnknowns": ["班次时间未知"],
    "requiredClarification": ["补充选课目标"],
    "forbiddenClaims": ["已确认为你排好课表"],
    "requiredSourceRefs": [],
}


class FakeTransport:
    """按调用顺序返回预设响应，记录每次请求体，便于断言构造结果。"""

    def __init__(self, planning: list[tuple[int, dict]] | None = None) -> None:
        self.planning = list(planning or [])
        self.calls: list[tuple[str, dict, dict]] = []

    def post(self, path, body, headers):
        self.calls.append((path, body, headers))
        if path.endswith("/sessions"):
            return 201, {"data": {"sessionToken": "token-1"}}
        if path.endswith("/academic-records"):
            # 落记录不受被测行为影响，固定回一条 id，让用例只关心目标端点的响应。
            return 201, envelope({"academicRecordId": "record:1"})
        status, payload = self.planning.pop(0)
        return status, payload


def envelope(data, issues=None) -> dict:
    return {
        "schemaVersion": "1.0",
        "requestId": "req-1",
        "traceId": "trace:1",
        "status": "OK",
        "data": data,
        "provenance": [],
        "issues": issues or [],
    }


def answer(**overrides) -> dict:
    base = {
        "taskId": "task:1",
        "traceId": "trace:1",
        "decision": "CLARIFY",
        "recommendations": [],
        "clarification": {"questionId": "goal:missing", "text": "补充选课目标", "choices": [], "allowFreeText": True},
        "unknowns": [],
        "usage": {"inputTokens": 100, "outputTokens": 50, "toolCalls": 1, "elapsedMs": 0},
    }
    base.update(overrides)
    return base


def write_case(tmp_path: Path, case_id="G2-001", group="G2") -> Path:
    cases = tmp_path / "cases"
    cases.mkdir(exist_ok=True)
    (cases / f"{case_id}.json").write_text(
        json.dumps(
            {
                "caseId": case_id,
                "groupId": group,
                "split": "evolution",
                "curriculumSnapshotId": "3c405feaa6d7",
                "offeringSnapshotId": None,
                "inputFixtureRef": f"fixtures/{case_id}.json",
                "userQuery": "别给我排早八",
                "rubricVersion": "rubric-d1-v1",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "fixtures").mkdir(exist_ok=True)
    (tmp_path / "fixtures" / f"{case_id}.json").write_text(
        json.dumps(
            {
                "promptText": "别给我排早八",
                "intent": {
                    "motives": ["SCHEDULE"],
                    "priorityOrder": [],
                    "hardConstraints": [],
                    "softPreferences": [],
                    "pinnedTeacherCoursePairs": [],
                    "interestTags": [],
                    "careerDirectionIds": [],
                },
                "offeringSnapshotId": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return cases


def make_runner(tmp_path: Path, transport, cases: Path) -> BenchmarkRunner:
    gold = tmp_path / "gold"
    gold.mkdir(exist_ok=True)
    (gold / "G2-001.json").write_text(json.dumps(GOLD, ensure_ascii=False), encoding="utf-8")
    return BenchmarkRunner(
        transport,
        cases_root=cases,
        gold_root=gold,
        contracts_root=ROOT / "contracts",
    )


# -- 请求构造 -------------------------------------------------------------
def test_planning_body_uses_fixture_intent() -> None:
    case = {"caseId": "G2-001", "groupId": "G2", "curriculumSnapshotId": "3c405feaa6d7", "userQuery": "别给我排早八"}
    fixture = {"promptText": "别给我排早八", "intent": INTENT}
    request = planning_body(case, fixture)
    assert request.body["intent"] == INTENT
    assert request.body["mode"] == "SIMULATION"
    assert request.body["offeringSnapshotId"] is None
    assert any("intent 取 fixture" in note for note in request.notes)


def test_planning_body_without_record_leaves_id_empty() -> None:
    """契约的 academicRecordId 必填，适配层不能编一个占位字符串，只能让上层先落空记录。"""
    case = {"caseId": "G2-001", "groupId": "G2", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"intent": INTENT, "academicRecordId": None}
    request = planning_body(case, fixture)
    assert request.body["academicRecordId"] is None
    assert any("空记录" in note for note in request.notes)


def test_planning_without_record_prepends_empty_record_step() -> None:
    from case_adapters import build_plan

    case = {"caseId": "G2-001", "groupId": "G2", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"intent": INTENT, "academicRecordId": None}
    plan = build_plan(case, fixture)
    assert [step.path for step in plan.steps] == ["/api/v1/academic-records", "/api/v1/planning"]
    assert plan.steps[0].body["transcriptComplete"] is False
    assert plan.steps[0].body["completedCourses"] == []


def test_desired_courses_become_pin_course() -> None:
    case = {"caseId": "G3-001", "groupId": "G3", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"desiredCourses": [{"courseCode": "08306128", "courseName": "Python计算"}]}
    request = planning_body(case, fixture)
    constraint = request.body["intent"]["hardConstraints"][0]
    assert constraint["kind"] == "PIN_COURSE"
    assert constraint["courseCode"] == "08306128"
    assert constraint["sourceText"] == "Python计算"


def test_tilde_course_code_folds_to_main_code() -> None:
    """原表用波浪号表示合上课：取主号作课标，原写法留在 sourceText，不造新编号。"""
    case = {"caseId": "G3-001", "groupId": "G3", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"desiredCourses": [{"courseCode": "08305009~010", "courseName": "数据结构(1-2)"}]}
    request = planning_body(case, fixture)
    constraint = request.body["intent"]["hardConstraints"][0]
    assert constraint["courseCode"] == "08305009"
    assert "08305009~010" in constraint["sourceText"]
    assert any("取主号" in note for note in request.notes)


def test_course_code_that_is_neither_id_nor_tilde_is_unsupported() -> None:
    case = {"caseId": "G3-001", "groupId": "G3", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"desiredCourses": [{"courseCode": "数据结构 1", "courseName": "数据结构"}]}
    with pytest.raises(UnsupportedCase):
        planning_body(case, fixture)


def test_fixture_with_only_record_keys_goes_audit_route() -> None:
    """缺资料类题面（G4-001）不是构造失败：落一条空记录再核查，让系统自己答未知。"""
    from case_adapters import build_plan

    plan = build_plan(
        {"caseId": "G4-001", "groupId": "G4", "curriculumSnapshotId": "3c405feaa6d7"},
        {"academicRecordId": None, "completedCourses": None},
    )
    assert plan.route == "AUDIT"
    assert plan.steps[0].body["completedCourses"] == []


def test_empty_fixture_is_unsupported() -> None:
    from case_adapters import build_plan

    with pytest.raises(UnsupportedCase):
        build_plan({"caseId": "GX-001", "groupId": "GX"}, {})


def test_answer_text_collects_structured_fields() -> None:
    text = answer_text(answer(unknowns=[{"code": "OFFERING_UNAVAILABLE", "message": "班次时间不可核验"}]))
    assert "补充选课目标" in text
    assert "班次时间不可核验" in text


# -- 判定分级 -------------------------------------------------------------
def test_pass_when_no_placeholder_and_not_blocked(tmp_path: Path) -> None:
    transport = FakeTransport([(200, envelope(answer()))])
    runner = make_runner(tmp_path, transport, write_case(tmp_path))
    outcome = runner.run_case(
        {
            "caseId": "G2-001",
            "groupId": "G2",
            "inputFixtureRef": "fixtures/G2-001.json",
            "curriculumSnapshotId": "3c405feaa6d7",
        }
    )
    assert outcome.status == PASS
    assert outcome.score is not None


def test_degraded_when_answer_carries_placeholder(tmp_path: Path) -> None:
    payload = envelope(answer(unknowns=[{"code": "FAKE_MODEL", "message": "占位模型"}]))
    runner = make_runner(tmp_path, FakeTransport([(200, payload)]), write_case(tmp_path))
    outcome = runner.run_case(
        {
            "caseId": "G2-001",
            "groupId": "G2",
            "inputFixtureRef": "fixtures/G2-001.json",
            "curriculumSnapshotId": "3c405feaa6d7",
        }
    )
    assert outcome.status == DEGRADED
    assert outcome.placeholders == ["FAKE_MODEL"]


def test_fail_when_forbidden_claim_matched(tmp_path: Path) -> None:
    payload = envelope(
        answer(recommendations=[{"courseCode": "CS1", "courseName": "已确认为你排好课表", "reason": ""}])
    )
    runner = make_runner(tmp_path, FakeTransport([(200, payload)]), write_case(tmp_path))
    outcome = runner.run_case(
        {
            "caseId": "G2-001",
            "groupId": "G2",
            "inputFixtureRef": "fixtures/G2-001.json",
            "curriculumSnapshotId": "3c405feaa6d7",
        }
    )
    assert outcome.blocked is True
    assert outcome.status == FAIL


def test_blocked_when_upstream_503(tmp_path: Path) -> None:
    payload = {"schemaVersion": "1.0", "status": "ERROR", "data": {}, "issues": [{"code": "TOOL_UNAVAILABLE"}]}
    runner = make_runner(tmp_path, FakeTransport([(503, payload)]), write_case(tmp_path))
    outcome = runner.run_case(
        {
            "caseId": "G2-001",
            "groupId": "G2",
            "inputFixtureRef": "fixtures/G2-001.json",
            "curriculumSnapshotId": "3c405feaa6d7",
        }
    )
    assert outcome.status == BLOCKED
    assert "TOOL_UNAVAILABLE" in (outcome.error or "")


# -- 成本与汇总 -----------------------------------------------------------
def test_missing_tokens_are_none_not_zero(tmp_path: Path) -> None:
    payload = envelope(answer(usage={"inputTokens": None, "outputTokens": None, "toolCalls": 3, "elapsedMs": 0}))
    runner = make_runner(tmp_path, FakeTransport([(200, payload)]), write_case(tmp_path))
    result = runner.run(MANIFEST)
    assert result["report"]["averageInputTokens"] is None
    assert result["report"]["averageOutputTokens"] is None
    assert result["summary"]["costCoverage"]["inputTokens"] == 0.0
    assert result["report"]["averageToolCalls"] == 3.0


def test_group_means_are_equal_weight(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    cases.mkdir()
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for case_id, group in (("G2-001", "G2"), ("G2-002", "G2"), ("G3-001", "G3")):
        (cases / f"{case_id}.json").write_text(
            json.dumps(
                {
                    "caseId": case_id,
                    "groupId": group,
                    "inputFixtureRef": f"fixtures/{case_id}.json",
                    "curriculumSnapshotId": "3c405feaa6d7",
                }
            ),
            encoding="utf-8",
        )
        (fixtures / f"{case_id}.json").write_text(json.dumps({"intent": INTENT}), encoding="utf-8")
    gold = tmp_path / "gold"
    gold.mkdir()
    for case_id in ("G2-001", "G2-002", "G3-001"):
        (gold / f"{case_id}.json").write_text(json.dumps(GOLD, ensure_ascii=False), encoding="utf-8")

    transport = FakeTransport(
        [
            (200, envelope(answer())),
            (200, envelope(answer(clarification=None, recommendations=[{"courseName": "x"}], unknowns=[]))),
            (200, envelope(answer())),
        ]
    )
    runner = BenchmarkRunner(transport, cases_root=cases, gold_root=gold, contracts_root=ROOT / "contracts")
    result = runner.run(MANIFEST)
    groups = result["summary"]["groupMeans"]
    assert set(groups) == {"G2", "G3"}
    assert result["summary"]["macroScore"] == round((groups["G2"] + groups["G3"]) / 2, 4)


def test_report_matches_contract(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, FakeTransport([(200, envelope(answer()))]), write_case(tmp_path))
    report = runner.run(MANIFEST)["report"]
    domain = json.loads((ROOT / "contracts" / "schemas" / "domain.schema.json").read_text(encoding="utf-8"))
    schema = {"$defs": domain["$defs"], "$ref": "#/$defs/RunReport"}
    assert list(Draft202012Validator(schema).iter_errors(report)) == []


def test_manifest_validation_reports_missing_fields() -> None:
    problems = validate_manifest({"schemaVersion": "1.0"}, load_manifest_schema(ROOT / "contracts"))
    assert problems


def test_write_outputs_writes_one_line_per_case(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, FakeTransport([(200, envelope(answer()))]), write_case(tmp_path))
    result = runner.run(MANIFEST)
    out = tmp_path / "out"
    paths = runner.write_outputs(result, out)
    lines = paths["cases"].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["caseId"] == "G2-001"
    assert json.loads(paths["report"].read_text(encoding="utf-8"))["decision"] == "BASELINE"


# -- 核查路线（academic-records + requirements/audit）----------------------
def write_audit_case(tmp_path: Path) -> Path:
    cases = tmp_path / "audit_cases"
    cases.mkdir(exist_ok=True)
    (cases / "G1-001.json").write_text(
        json.dumps(
            {
                "caseId": "G1-001",
                "groupId": "G1",
                "curriculumSnapshotId": "3c405feaa6d7",
                "inputFixtureRef": "audit_fixtures/G1-001.json",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixtures = tmp_path / "audit_fixtures"
    fixtures.mkdir(exist_ok=True)
    (fixtures / "G1-001.json").write_text(
        json.dumps(
            {
                "promptText": "我还差多少学分",
                "completedCourses": [{"courseCode": "08305011", "credits": 5.0, "termIndex": 1}],
                "transcriptComplete": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return cases


AUDIT_DATA = {
    "curriculumSnapshotId": "3c405feaa6d7",
    "academicRecordId": "record:1",
    "recordRevision": 1,
    "transcriptComplete": True,
    "requirements": [
        {
            "requirementId": "req:1",
            "courseCodes": ["08305011"],
            "requiredCredits": 4,
            "earnedCredits": 2,
            "gapCredits": 2,
            "state": "UNSATISFIED",
            "sourceRefIds": ["cs2024-s1-A49"],
        }
    ],
    "suggestedCourseCodes": [],
    "unknowns": [{"code": "OFFERING_UNAVAILABLE", "message": "本学期班次不可核验"}],
}


def test_audit_route_runs_two_steps(tmp_path: Path) -> None:
    cases = write_audit_case(tmp_path)
    gold = tmp_path / "gold_audit"
    gold.mkdir()
    (gold / "G1-001.json").write_text(json.dumps(GOLD, ensure_ascii=False), encoding="utf-8")
    transport = FakeTransport([(200, envelope(AUDIT_DATA))])
    runner = BenchmarkRunner(transport, cases_root=cases, gold_root=gold, contracts_root=ROOT / "contracts")
    outcome = runner.run_case(
        {
            "caseId": "G1-001",
            "groupId": "G1",
            "inputFixtureRef": "audit_fixtures/G1-001.json",
            "curriculumSnapshotId": "3c405feaa6d7",
        }
    )
    assert outcome.route == "AUDIT"
    assert outcome.status in (PASS, DEGRADED, FAIL)
    paths = [call[0] for call in transport.calls]
    assert paths[1].endswith("/academic-records")
    assert paths[2].endswith("/requirements/audit")
    assert transport.calls[2][1]["academicRecordId"] == "record:1"


def test_audit_second_step_failure_names_the_step(tmp_path: Path) -> None:
    cases = write_audit_case(tmp_path)
    gold = tmp_path / "gold_audit"
    gold.mkdir()
    (gold / "G1-001.json").write_text(json.dumps(GOLD, ensure_ascii=False), encoding="utf-8")
    transport = FakeTransport([(503, {"issues": [{"code": "TOOL_UNAVAILABLE"}]})])
    runner = BenchmarkRunner(transport, cases_root=cases, gold_root=gold, contracts_root=ROOT / "contracts")
    outcome = runner.run_case(
        {
            "caseId": "G1-001",
            "groupId": "G1",
            "inputFixtureRef": "audit_fixtures/G1-001.json",
            "curriculumSnapshotId": "3c405feaa6d7",
        }
    )
    assert outcome.status == BLOCKED
    assert "第 2 步" in (outcome.error or "")
    assert "TOOL_UNAVAILABLE" in (outcome.error or "")


def test_audit_body_records_outcome_assumption(tmp_path: Path) -> None:
    cases = write_audit_case(tmp_path)
    runner = BenchmarkRunner(FakeTransport([]), cases_root=cases, gold_root=tmp_path, contracts_root=ROOT / "contracts")
    fixture = runner.load_fixture("audit_fixtures/G1-001.json", tmp_path)
    from case_adapters import build_plan

    plan = build_plan({"caseId": "G1-001", "groupId": "G1", "curriculumSnapshotId": "3c405feaa6d7"}, fixture)
    body = plan.steps[0].body
    assert body["completedCourses"][0]["outcome"] == "PASSED"
    assert any("兜底" in note for note in plan.notes)
