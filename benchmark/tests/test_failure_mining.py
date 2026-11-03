"""D-F4 归因骨架自测：门槛、排除、白名单、结构齐备。

不测模型表现，只钉住归因规则：单例不产假设、环境未接线不进归因、候选只指向 Harness 白名单。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from failure_mining import HARNESS_WHITELIST, MIN_CASES, FailureMiner, mine_file


def case(case_id: str, *, status="FAIL", verdicts=None, placeholders=None, error=None) -> dict:
    return {
        "caseId": case_id,
        "groupId": "G2",
        "status": status,
        "placeholders": placeholders or [],
        "error": error,
        "scoreReport": {"verdicts": verdicts or []},
    }


def missed(kind: str, text: str) -> dict:
    return {"kind": kind, "text": text, "matched": False, "mode": "text", "note": ""}


def test_two_cases_same_failure_make_one_hypothesis() -> None:
    cases = [
        case("G2-001", verdicts=[missed("requiredUnknowns", "没有班次数据，无法给出具体课表")]),
        case("G2-002", verdicts=[missed("requiredUnknowns", "没有班次数据，无法给出具体课表")]),
    ]
    result = FailureMiner().mine(cases)
    assert len(result["hypotheses"]) == 1
    hypothesis = result["hypotheses"][0]
    assert hypothesis["caseIds"] == ["G2-001", "G2-002"]
    assert hypothesis["category"] == "未知与澄清"


def test_single_case_failure_is_rejected_not_dropped() -> None:
    cases = [case("G2-001", verdicts=[missed("requiredFacts", "通识课要求 4 学分")])]
    result = FailureMiner().mine(cases)
    assert result["hypotheses"] == []
    assert len(result["rejected"]) == 1
    assert str(MIN_CASES) in result["rejected"][0]["reason"]


def test_different_failure_kinds_are_not_merged() -> None:
    cases = [
        case("G2-001", verdicts=[missed("requiredFacts", "甲事实")]),
        case("G2-002", verdicts=[missed("requiredFacts", "甲事实")]),
        case("G2-003", verdicts=[missed("requiredClarification", "请提供已修记录")]),
        case("G2-004", verdicts=[missed("requiredClarification", "请提供已修记录")]),
    ]
    result = FailureMiner().mine(cases)
    assert len(result["hypotheses"]) == 2
    assert {item["category"] for item in result["hypotheses"]} == {"事实覆盖", "未知与澄清"}


def test_forbidden_claim_hit_becomes_unsupported_claim_category() -> None:
    verdict = {
        "kind": "forbiddenClaims",
        "text": "不得声称全英语要求已满足",
        "matched": True,
        "mode": "text",
        "note": "",
    }
    cases = [case("G1-001", verdicts=[verdict]), case("G1-002", verdicts=[dict(verdict)])]
    result = FailureMiner().mine(cases)
    assert result["hypotheses"][0]["category"] == "无依据主张"


def test_allowed_targets_stay_inside_harness_whitelist() -> None:
    cases = [
        case("G2-001", verdicts=[missed("requiredClarification", "请提供已修记录")]),
        case("G2-002", verdicts=[missed("requiredClarification", "请提供已修记录")]),
    ]
    hypothesis = FailureMiner().mine(cases)["hypotheses"][0]
    assert hypothesis["allowedTargets"]
    assert all(target in HARNESS_WHITELIST for target in hypothesis["allowedTargets"])


def test_environment_gap_cases_are_excluded() -> None:
    cases = [
        case("G1-001", status="DEGRADED", placeholders=["FAKE_TOOL"], verdicts=[missed("requiredFacts", "同一个事实")]),
        case("G1-002", status="DEGRADED", placeholders=["FAKE_TOOL"], verdicts=[missed("requiredFacts", "同一个事实")]),
        case("G3-001", status="BLOCKED", error="构造：编号不合契约"),
    ]
    result = FailureMiner().mine(cases)
    assert result["hypotheses"] == []
    assert len(result["excluded"]) == 3
    assert any("FAKE_TOOL" in item["reason"] for item in result["excluded"])


def test_hypothesis_has_all_documented_fields() -> None:
    cases = [
        case("G2-001", verdicts=[missed("requiredUnknowns", "时间未知")]),
        case("G2-002", verdicts=[missed("requiredUnknowns", "时间未知")]),
    ]
    hypothesis = FailureMiner().mine(cases)["hypotheses"][0]
    for key in (
        "hypothesisId",
        "category",
        "caseIds",
        "pattern",
        "likelyCause",
        "allowedTargets",
        "expectedMetric",
        "traceRefs",
    ):
        assert key in hypothesis


def test_mine_file_reads_cases_jsonl(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rows = [
        case("G2-001", verdicts=[missed("requiredUnknowns", "时间未知")]),
        case("G2-002", verdicts=[missed("requiredUnknowns", "时间未知")]),
    ]
    (run_dir / "cases.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
    )
    result = mine_file(run_dir / "cases.jsonl")
    assert result["summary"]["hypothesisCount"] == 1
    assert result["summary"]["caseCount"] == 2
