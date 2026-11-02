from __future__ import annotations

import json
from pathlib import Path

from case_adapters import UnsupportedCase, record_body
from runner import DEGRADED, UNSCORED, BenchmarkRunner, load_manifest_schema, validate_manifest

ROOT = Path(__file__).resolve().parents[2]


class SyntheticTransport:
    placeholder_code = "FAKE_MODEL"

    def __init__(self) -> None:
        self.posts: list[tuple[str, dict, dict]] = []

    def post(self, path: str, body: dict, headers: dict) -> tuple[int, dict]:
        self.posts.append((path, body, headers))
        if path == "/api/v1/sessions":
            return 201, {"data": {"sessionToken": "synthetic-session"}}
        return 200, {
            "data": {
                "decision": "CLARIFY",
                "clarification": {"text": "请补充目标。"},
                "unknowns": [{"code": "FAKE_MODEL", "message": "synthetic controlled model"}],
                "usage": {"inputTokens": None, "outputTokens": None, "toolCalls": 0, "elapsedMs": 1},
            }
        }

    def get(self, path: str, params: dict, headers: dict) -> tuple[int, dict]:
        raise AssertionError("synthetic case should use POST /planning only")


def test_synthetic_smoke_case_runs_through_current_contract_adapter(tmp_path: Path) -> None:
    transport = SyntheticTransport()
    runner = BenchmarkRunner(
        transport,
        cases_root=ROOT / "benchmark" / "cases" / "smoke",
        gold_root=None,
        contracts_root=ROOT / "contracts",
    )
    cases = [json.loads((ROOT / "benchmark/cases/smoke/SYN-002.json").read_text())]
    outcome = runner.run_case(cases[0], repo_root=ROOT)

    assert outcome.status == UNSCORED
    assert outcome.assessment_status == "DEGRADED_SYNTHETIC"
    assert outcome.placeholders == ["FAKE_MODEL"]
    assert outcome.input_tokens is None
    assert transport.posts[1][0] == "/api/v1/planning"
    assert transport.posts[1][1] == cases[0]["request"]
    assert transport.posts[1][2]["Authorization"] == "Bearer synthetic-session"

    manifest = json.loads((ROOT / "benchmark/manifests/synthetic-smoke.json").read_text())
    assert validate_manifest(manifest, load_manifest_schema(ROOT / "contracts")) == []
    output = tmp_path / "run"
    result = {
        "manifest": manifest,
        "report": runner.build_report(manifest, [outcome]),
        "summary": runner.build_summary([outcome]),
        "outcomes": [outcome],
        "repeatDiffs": [],
    }
    runner.write_outputs(result, output)
    saved = json.loads((output / "cases.jsonl").read_text().splitlines()[0])
    assert saved["assessmentStatus"] == "DEGRADED_SYNTHETIC"
    assert saved["status"] == UNSCORED
    assert json.loads((output / "run-report.json").read_text())["heldOutScore"] is None


def test_synthetic_placeholder_is_not_a_quality_pass() -> None:
    transport = SyntheticTransport()
    runner = BenchmarkRunner(
        transport,
        cases_root=ROOT / "benchmark" / "cases" / "smoke",
        gold_root=None,
        contracts_root=ROOT / "contracts",
    )
    result = runner.run(
        {"runId": "synthetic-check", "harnessVersion": "test", "parentVersion": None, "repeatCount": 1},
        repo_root=ROOT,
        repeats=2,
    )
    assert result["manifest"]["repeatCount"] == 2
    assert result["summary"]["repeatStable"] is True
    assert result["summary"]["scoredCount"] == 0
    assert all(item.status not in {DEGRADED, "PASS"} for item in result["outcomes"])


def test_interval_course_number_and_missing_transcript_completeness_are_conservative() -> None:
    from case_adapters import _constraints_from_desired

    try:
        _constraints_from_desired([{"courseCode": "CS101~102", "courseName": "Synthetic pair"}])
    except UnsupportedCase:
        pass
    else:
        raise AssertionError("compound course id must not be reduced to its first part")

    body, _ = record_body({"curriculumSnapshotId": "curr:demo"}, {"completedCourses": []})
    assert body["transcriptComplete"] is False


def test_replan_case_is_marked_unmeasured_without_http_calls() -> None:
    case = {
        "caseId": "synthetic-replan",
        "groupId": "G3",
        "curriculumSnapshotId": "curr:demo",
        "inputFixtureRef": "fixture.json",
    }
    from case_adapters import build_plan

    plan = build_plan(case, {"originalGoal": "old", "newGoal": "new"})
    assert plan.steps == []
    assert "未测" in plan.notes[-1]


def test_transport_timeout_is_recorded_as_a_case_failure() -> None:
    class TimeoutTransport(SyntheticTransport):
        def post(self, path: str, body: dict, headers: dict) -> tuple[int, dict]:
            if path != "/api/v1/sessions":
                raise TimeoutError("timeout with no response body")
            return super().post(path, body, headers)

    transport = TimeoutTransport()
    runner = BenchmarkRunner(
        transport,
        cases_root=ROOT / "benchmark" / "cases" / "smoke",
        gold_root=None,
        contracts_root=ROOT / "contracts",
    )
    case = json.loads((ROOT / "benchmark/cases/smoke/SYN-002.json").read_text())
    outcome = runner.run_case(case, repo_root=ROOT)
    assert outcome.status == "BLOCKED"
    assert outcome.error == "第 1 步 规划请求：HTTP 调用失败（TimeoutError）"
    assert "timeout with no response body" not in outcome.error


def test_only_double_reviewed_matching_gold_is_eligible(tmp_path: Path) -> None:
    case = {
        "caseId": "G1-001",
        "groupId": "G1",
        "rubricVersion": "rubric-v1",
    }
    gold_path = tmp_path / "G1-001.json"
    gold = {
        "caseId": "G1-001",
        "groupId": "G1",
        "status": "draft",
        "reviewerIds": ["reviewer-a", "reviewer-b"],
        "requiredFacts": ["required fact"],
        "requiredUnknowns": ["required unknown"],
        "requiredClarification": ["required clarification"],
        "forbiddenClaims": ["forbidden claim"],
        "requiredSourceRefs": [{}],
        "rubricVersion": "rubric-v1",
    }
    gold_path.write_text(json.dumps(gold))
    runner = BenchmarkRunner(SyntheticTransport(), cases_root=tmp_path, gold_root=tmp_path)

    eligible, issue = runner.load_gold(case)
    assert eligible is None
    assert "status=reviewed" in issue

    gold["status"] = "reviewed"
    gold["reviewerIds"] = ["reviewer-a", "reviewer-a"]
    gold_path.write_text(json.dumps(gold))
    eligible, issue = runner.load_gold(case)
    assert eligible is None
    assert "双人复核" in issue

    gold["reviewerIds"] = ["reviewer-a", "reviewer-b"]
    gold_path.write_text(json.dumps(gold))
    eligible, issue = runner.load_gold(case)
    assert issue is None
    assert eligible["status"] == "reviewed"
