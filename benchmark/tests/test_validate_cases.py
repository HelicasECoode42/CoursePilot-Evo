"""D1 案例校验器的正反例测试。

正例：一份最小合法案例必须零 ERROR。
反例：每种能被机器判出的错误各造一条，必须报出对应错误码。
真实案例集另有单独一条测试，需要工作区外的私有标注目录，只在本地运行。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

import validate_cases as vc

# 题面在仓库内，任何检出都有；标注在工作区外（仓库公开，不能进库），CI 的干净检出没有。
REAL_PROMPT = ROOT / "benchmark" / "cases" / "evolution" / "G1-001.json"
REAL_GOLD = ROOT.parent / "restricted" / "gold" / "G1-001.json"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def synth_gold(prompt):
    """按题面造一份最小合法标注。

    不读工作区外的真实标注，测试才能在干净检出上跑：CI 拿不到私有标注目录。
    """
    return {
        "caseId": prompt["caseId"],
        "groupId": prompt["groupId"],
        "status": "draft",
        "reviewerIds": ["mira-xu", "goat-yang"],
        "reviewedBy": [],
        "rubricVersion": prompt["rubricVersion"],
        "requiredFacts": ["当学期只限选通识课 4 学分或《线性代数》3 学分其中之一。"],
        "requiredUnknowns": ["已修记录不含全英语授课课程，该要求是否满足无法判断。"],
        "requiredClarification": ["请提供已修课程记录以确定该选哪一门。"],
        "forbiddenClaims": ["不得声称可以同时选修通识课 4 学分与《线性代数》。"],
        "requiredSourceRefs": [
            {
                "kind": "CURRICULUM",
                "refId": "synth-ref-1",
                "snapshotId": prompt["curriculumSnapshotId"],
                "locator": "计科学1（非直招）A49",
                "capturedAt": "2026-10-08T00:00:00Z",
            }
        ],
    }


@pytest.fixture
def case_set(tmp_path):
    """在临时目录里搭一套完整案例，返回 (cases_root, gold_root, prompt, gold)。"""
    cases = tmp_path / "evolution"
    gold = tmp_path / "gold"
    cases.mkdir()
    gold.mkdir()
    prompt = load(REAL_PROMPT)
    goldj = synth_gold(prompt)
    (cases / "G1-001.json").write_text(json.dumps(prompt, ensure_ascii=False), encoding="utf-8")
    (gold / "G1-001.json").write_text(json.dumps(goldj, ensure_ascii=False), encoding="utf-8")
    return cases, gold, prompt, goldj


def codes(errors):
    return [c for c, _ in errors]


def test_synthetic_case_has_no_error(case_set):
    cases, gold, _, _ = case_set
    results, errors, warnings = vc.validate_collection(cases, gold)
    assert results, "\u81f3\u5c11\u8981\u6709\u4e00\u6761\u6848\u4f8b"
    assert errors == [], errors
    assert any(c == "W02" for c in codes(warnings)), "\u672a\u590d\u6838\u6848\u4f8b\u5e94\u7ed9 W02 \u8b66\u544a"


@pytest.mark.skipif(
    not REAL_GOLD.is_file(),
    reason="\u9700\u8981\u5de5\u4f5c\u533a\u5916\u7684\u79c1\u6709\u6807\u6ce8\u76ee\u5f55\uff0cCI \u5e72\u51c0\u68c0\u51fa\u4e0d\u5177\u5907",
)
def test_real_case_has_no_error():
    results, errors, warnings = vc.validate_collection(
        ROOT / "benchmark" / "cases" / "evolution", ROOT.parent / "restricted" / "gold"
    )
    assert results
    assert errors == [], errors
    assert any(c == "W02" for c in codes(warnings))


def test_answer_fields_leak_into_prompt(case_set, monkeypatch):
    cases, gold, prompt, _ = case_set
    prompt["requiredFacts"] = ["\u6f0f\u51fa\u6765\u7684\u7b54\u6848"]
    (cases / "G1-001.json").write_text(json.dumps(prompt, ensure_ascii=False), encoding="utf-8")
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E06" in codes(errors), errors


def test_missing_gold_file(case_set):
    cases, gold, _, _ = case_set
    (gold / "G1-001.json").unlink()
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E02" in codes(errors), errors


def test_source_ref_snapshot_mismatch(case_set, monkeypatch):
    cases, gold, _, goldj = case_set
    goldj["requiredSourceRefs"][0]["snapshotId"] = "ffffffffffff"
    (gold / "G1-001.json").write_text(json.dumps(goldj, ensure_ascii=False), encoding="utf-8")
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E07" in codes(errors), errors


def test_non_ascii_ref_id_rejected(case_set):
    cases, gold, _, goldj = case_set
    goldj["requiredSourceRefs"][0]["refId"] = "\u8ba1\u79d1\u5b661!A49"
    (gold / "G1-001.json").write_text(json.dumps(goldj, ensure_ascii=False), encoding="utf-8")
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E08" in codes(errors), errors


def test_empty_required_facts(case_set):
    cases, gold, _, goldj = case_set
    goldj["requiredFacts"] = []
    (gold / "G1-001.json").write_text(json.dumps(goldj, ensure_ascii=False), encoding="utf-8")
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E09" in codes(errors) or "E03" in codes(errors), errors


def test_single_reviewer(case_set):
    cases, gold, _, goldj = case_set
    goldj["reviewerIds"] = ["mira-xu"]
    (gold / "G1-001.json").write_text(json.dumps(goldj, ensure_ascii=False), encoding="utf-8")
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E10" in codes(errors) or "E03" in codes(errors), errors


def test_missing_fixture_file(case_set, tmp_path, monkeypatch):
    cases, gold, prompt, _ = case_set
    prompt["inputFixtureRef"] = "benchmark/cases/fixtures/not-there.json"
    (cases / "G1-001.json").write_text(json.dumps(prompt, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        vc, "ROOT", tmp_path
    )  # fixture \u6309\u4ed3\u5e93\u6839\u89e3\u6790\uff0c\u6307\u5230 tmp \u5373\u53ef\u9020\u7f3a\u5931
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E11" in codes(errors), errors


def test_split_not_matching_folder(case_set):
    cases, gold, prompt, _ = case_set
    prompt["split"] = "held-out"
    (cases / "G1-001.json").write_text(json.dumps(prompt, ensure_ascii=False), encoding="utf-8")
    _, errors, _ = vc.validate_collection(cases, gold)
    assert "E05" in codes(errors), errors


def test_cli_exit_code_is_nonzero_on_error(tmp_path, case_set):
    cases, gold, prompt, _ = case_set
    prompt["userQuery"] = "\u77ed"  # \u4f4e\u4e8e schema \u6700\u5c0f\u957f\u5ea6
    (cases / "G1-001.json").write_text(json.dumps(prompt, ensure_ascii=False), encoding="utf-8")
    rc = vc.main(["--cases-root", str(cases), "--gold-root", str(gold)])
    assert rc == 1
