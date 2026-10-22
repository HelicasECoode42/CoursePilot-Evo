"""held-out 隔离自测：路径约束、软链拒绝、只输出聚合、失败不伪造分数。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from heldout import IsolationError, assert_outside_workspace, run_heldout

GOLD = {
    "caseId": "H-001",
    "requiredFacts": ["这条判据句子不得出现在子进程输出里"],
    "requiredUnknowns": ["班次时间未知"],
    "requiredClarification": ["请提供已修记录"],
    "forbiddenClaims": ["不得声称已排好课表"],
    "requiredSourceRefs": [],
}


def make_heldout(tmp_path: Path) -> tuple[Path, Path]:
    cases = tmp_path / "heldout"
    gold = tmp_path / "gold"
    fixtures = cases / "fixtures"
    fixtures.mkdir(parents=True)
    gold.mkdir()
    (cases / "H-001.json").write_text(
        json.dumps(
            {
                "caseId": "H-001",
                "groupId": "G2",
                "curriculumSnapshotId": "3c405feaa6d7",
                "inputFixtureRef": "fixtures/H-001.json",
                "userQuery": "帮我排课",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (fixtures / "H-001.json").write_text(
        json.dumps(
            {
                "intent": {
                    "motives": ["SCHEDULE"],
                    "priorityOrder": [],
                    "hardConstraints": [],
                    "softPreferences": [],
                    "pinnedTeacherCoursePairs": [],
                    "interestTags": [],
                    "careerDirectionIds": [],
                },
                "academicRecordId": "record:test",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (gold / "H-001.json").write_text(json.dumps(GOLD, ensure_ascii=False), encoding="utf-8")
    return cases, gold


def test_directory_inside_workspace_is_refused(tmp_path: Path) -> None:
    inner = ROOT / "benchmark" / "tests"
    with pytest.raises(IsolationError):
        assert_outside_workspace(inner, ROOT, label="测试目录")


def test_directory_outside_workspace_is_accepted(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    assert assert_outside_workspace(outside, ROOT, label="外部目录") == outside.resolve()


def test_symlink_on_path_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建软链")
    with pytest.raises(IsolationError):
        assert_outside_workspace(link, ROOT, label="软链目录")


def test_dry_worker_returns_aggregate_only(tmp_path: Path) -> None:
    cases, gold = make_heldout(tmp_path)
    payload = run_heldout(
        cases_root=cases,
        gold_root=gold,
        manifest_path=ROOT / "benchmark" / "manifests" / "example.json",
        workspace_root=ROOT,
        transport="dry",
        timeout=180,
    )
    assert payload["leakFree"] is True
    assert payload["caseCount"] == 1
    assert "verdicts" not in json.dumps(payload)
    assert payload["heldOutScore"] is not None


def test_worker_output_has_no_claim_text(tmp_path: Path) -> None:
    cases, gold = make_heldout(tmp_path)
    payload = run_heldout(
        cases_root=cases,
        gold_root=gold,
        manifest_path=ROOT / "benchmark" / "manifests" / "example.json",
        workspace_root=ROOT,
        transport="dry",
        timeout=180,
    )
    dumped = json.dumps(payload, ensure_ascii=False)
    for claim in GOLD["requiredFacts"] + GOLD["forbiddenClaims"]:
        assert claim[:12] not in dumped


def test_missing_gold_directory_raises(tmp_path: Path) -> None:
    cases, _ = make_heldout(tmp_path)
    with pytest.raises(IsolationError):
        run_heldout(
            cases_root=cases,
            gold_root=tmp_path / "nope",
            manifest_path=ROOT / "benchmark" / "manifests" / "example.json",
            workspace_root=ROOT,
            transport="dry",
            timeout=120,
        )
