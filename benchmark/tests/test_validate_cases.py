"""D1 案例校验器的正反例测试。

正例：真实案例目录（题面在仓库内、标注在工作区外）必须零 ERROR。
反例：每种能被机器判出的错误各造一条，必须报出对应错误码。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

import validate_cases as vc

REAL_PROMPT = ROOT / "benchmark" / "cases" / "evolution" / "G1-001.json"
REAL_GOLD = ROOT.parent / "restricted" / "gold" / "G1-001.json"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@pytest.fixture
def case_set(tmp_path):
    """把真实案例复制到临时目录，返回 (cases_root, gold_root, prompt, gold)。"""
    cases = tmp_path / "evolution"
    gold = tmp_path / "gold"
    cases.mkdir()
    gold.mkdir()
    prompt = load(REAL_PROMPT)
    goldj = load(REAL_GOLD)
    (cases / "G1-001.json").write_text(json.dumps(prompt, ensure_ascii=False), encoding="utf-8")
    (gold / "G1-001.json").write_text(json.dumps(goldj, ensure_ascii=False), encoding="utf-8")
    return cases, gold, prompt, goldj


def codes(errors):
    return [c for c, _ in errors]


def test_real_case_has_no_error():
    results, errors, warnings = vc.validate_collection(
        ROOT / "benchmark" / "cases" / "evolution", ROOT.parent / "restricted" / "gold"
    )
    assert results, "至少要有一条案例"
    assert errors == [], errors
    assert any(c == "W02" for c in codes(warnings)), "未复核案例应给 W02 警告"


def test_answer_fields_leak_into_prompt(case_set, monkeypatch):
    cases, gold, prompt, _ = case_set
    prompt["requiredFacts"] = ["漏出来的答案"]
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
    goldj["requiredSourceRefs"][0]["refId"] = "计科学1!A49"
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
    monkeypatch.setattr(vc, "ROOT", tmp_path)  # fixture 按仓库根解析，指到 tmp 即可造缺失
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
    prompt["userQuery"] = "短"  # 低于 schema 最小长度
    (cases / "G1-001.json").write_text(json.dumps(prompt, ensure_ascii=False), encoding="utf-8")
    rc = vc.main(["--cases-root", str(cases), "--gold-root", str(gold)])
    assert rc == 1
