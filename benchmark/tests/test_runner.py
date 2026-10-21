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
    fixture = {"promptText": "别给我排早八", "intent": {"motives": ["SCHEDULE"]}}
    request = planning_body(case, fixture)
    assert request.body["intent"] == {"motives": ["SCHEDULE"]}
    assert request.body["mode"] == "SIMULATION"
    assert request.body["offeringSnapshotId"] is None
    assert any("intent 取 fixture" in note for note in request.notes)


def test_planning_body_missing_record_uses_placeholder() -> None:
    case = {"caseId": "G2-001", "groupId": "G2", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"intent": {"motives": ["SCHEDULE"]}, "academicRecordId": None}
    request = planning_body(case, fixture)
    assert request.body["academicRecordId"] == "rec-not-provided"
    assert any("占位符" in note for note in request.notes)


def test_desired_courses_become_pin_course() -> None:
    case = {"caseId": "G3-001", "groupId": "G3", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"desiredCourses": [{"courseCode": "08306128", "courseName": "Python计算"}]}
    request = planning_body(case, fixture)
    constraint = request.body["intent"]["hardConstraints"][0]
    assert constraint["kind"] == "PIN_COURSE"
    assert constraint["courseCode"] == "08306128"
    assert constraint["sourceText"] == "Python计算"


def test_course_code_outside_contract_charset_is_unsupported() -> None:
    """fixture 里 08305009~010 这种编号过不了契约 Id 字符集，必须判 BLOCKED 而不是硬塞。"""
    case = {"caseId": "G3-001", "groupId": "G3", "curriculumSnapshotId": "3c405feaa6d7"}
    fixture = {"desiredCourses": [{"courseCode": "08305009~010", "courseName": "数据结构(1-2)"}]}
    with pytest.raises(UnsupportedCase):
        planning_body(case, fixture)


def test_fixture_without_intent_or_courses_is_unsupported() -> None:
    with pytest.raises(UnsupportedCase):
        planning_body({"caseId": "G1-001"}, {"academicRecordId": None, "completedCourses": None})


def test_answer_text_collects_structured_fields() -> None:
    text = answer_text(answer(unknowns=[{"code": "OFFERING_UNAVAILABLE", "message": "班次时间不可核验"}]))
    assert "补充选课目标" in text
    assert "班次时间不可核验" in text


# -- 判定分级 -------------------------------------------------------------
def test_pass_when_no_placeholder_and_not_blocked(tmp_path: Path) -> None:
    transport = FakeTransport([(200, envelope(answer()))])
    runner = make_runner(tmp_path, transport, write_case(tmp_path))
    outcome = runner.run_case({"caseId": "G2-001", "groupId": "G2", "inputFixtureRef": "fixtures/G2-001.json"})
    assert outcome.status == PASS
    assert outcome.score is not None


def test_degraded_when_answer_carries_placeholder(tmp_path: Path) -> None:
    payload = envelope(answer(unknowns=[{"code": "FAKE_MODEL", "message": "占位模型"}]))
    runner = make_runner(tmp_path, FakeTransport([(200, payload)]), write_case(tmp_path))
    outcome = runner.run_case({"caseId": "G2-001", "groupId": "G2", "inputFixtureRef": "fixtures/G2-001.json"})
    assert outcome.status == DEGRADED
    assert outcome.placeholders == ["FAKE_MODEL"]


def test_fail_when_forbidden_claim_matched(tmp_path: Path) -> None:
    payload = envelope(
        answer(recommendations=[{"courseCode": "CS1", "courseName": "已确认为你排好课表", "reason": ""}])
    )
    runner = make_runner(tmp_path, FakeTransport([(200, payload)]), write_case(tmp_path))
    outcome = runner.run_case({"caseId": "G2-001", "groupId": "G2", "inputFixtureRef": "fixtures/G2-001.json"})
    assert outcome.blocked is True
    assert outcome.status == FAIL


def test_blocked_when_upstream_503(tmp_path: Path) -> None:
    payload = {"schemaVersion": "1.0", "status": "ERROR", "data": {}, "issues": [{"code": "TOOL_UNAVAILABLE"}]}
    runner = make_runner(tmp_path, FakeTransport([(503, payload)]), write_case(tmp_path))
    outcome = runner.run_case({"caseId": "G2-001", "groupId": "G2", "inputFixtureRef": "fixtures/G2-001.json"})
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
            json.dumps({"caseId": case_id, "groupId": group, "inputFixtureRef": f"fixtures/{case_id}.json"}),
            encoding="utf-8",
        )
        (fixtures / f"{case_id}.json").write_text(json.dumps({"intent": {"motives": ["SCHEDULE"]}}), encoding="utf-8")
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
