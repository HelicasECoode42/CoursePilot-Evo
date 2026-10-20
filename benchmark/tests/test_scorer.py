"""评分器骨架的自测：用假 answer 与假匹配器钉住计分口径。

不测语义（那是模型与 Runner 的事），只测规则：命中怎么记、漏答怎么算、
出现禁止结论或引用核不过时怎么归零、JavaVerifier 未接线时怎么如实标记。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from scoring.scorer import keyword_matcher, score, score_many


def substr_matcher(claim, answer):
    """测试用匹配器：判据句子原样出现在答案里即算命中。"""
    return claim in answer


GOLD = {
    "caseId": "G9-001",
    "requiredFacts": ["通识课总计要求 4 学分", "当学期只能二选一"],
    "requiredUnknowns": ["是否已修过《线性代数》未知"],
    "requiredClarification": ["请提供已修课程记录"],
    "forbiddenClaims": ["可以同时选修通识课与《线性代数》"],
    "requiredSourceRefs": [
        {
            "kind": "CURRICULUM",
            "refId": "cs2024-s1-A49",
            "snapshotId": "3c405feaa6d7",
            "locator": "计科学1（非直招）A49",
            "capturedAt": "2026-10-08T00:00:00Z",
        }
    ],
}

FULL = "通识课总计要求 4 学分；当学期只能二选一；是否已修过《线性代数》未知；请提供已修课程记录"


class OkVerifier:
    def verify_source_ref(self, ref):
        return None


class BadVerifier:
    def verify_source_ref(self, ref):
        return "快照不一致"


def test_full_answer_scores_one():
    r = score(FULL, GOLD, matcher=substr_matcher)
    assert r.blocked is False
    assert r.score == 1.0
    assert r.counts() == {"requiredFacts": 2, "requiredUnknowns": 1, "requiredClarification": 1, "forbiddenClaims": 1}


def test_partial_answer_scores_below_one():
    r = score("通识课总计要求 4 学分", GOLD, matcher=substr_matcher)
    assert r.blocked is False
    assert r.coverage == pytest.approx(1 / 4)
    assert r.score == pytest.approx(0.25)


def test_missing_unknown_costs_points():
    answer = "通识课总计要求 4 学分；当学期只能二选一；请提供已修课程记录"
    r = score(answer, GOLD, matcher=substr_matcher)
    assert r.score == pytest.approx(3 / 4)


def test_forbidden_claim_blocks_and_zeroes():
    r = score(FULL + "；可以同时选修通识课与《线性代数》", GOLD, matcher=substr_matcher)
    assert r.blocked is True
    assert r.score == 0.0
    hit = [v for v in r.verdicts if v.kind == "forbiddenClaims" and v.matched]
    assert len(hit) == 1 and hit[0].note


def test_empty_answer_scores_zero_without_block():
    r = score("", GOLD, matcher=substr_matcher)
    assert r.score == 0.0
    assert r.blocked is False


def test_refs_unverified_without_java_verifier():
    r = score(FULL, GOLD, matcher=substr_matcher)
    assert [x.status for x in r.refs] == ["unverified"]
    assert r.java_verifier is False
    assert r.blocked is False


def test_failed_ref_verification_blocks():
    r = score(FULL, GOLD, matcher=substr_matcher, java_verifier=BadVerifier())
    assert [x.status for x in r.refs] == ["failed"]
    assert r.blocked is True and r.score == 0.0
    assert "快照不一致" in r.refs[0].note


def test_passing_java_verifier_keeps_score():
    r = score(FULL, GOLD, matcher=substr_matcher, java_verifier=OkVerifier())
    assert [x.status for x in r.refs] == ["verified"]
    assert r.score == 1.0


def test_default_keyword_matcher_hits_identical_sentence():
    claim = "学校不发布班级平均分与成绩分布"
    assert keyword_matcher(claim, "据我所知，" + claim + "，因此无法给出排序") is True
    assert keyword_matcher(claim, "我给不出这门课的平均分排序") is False


def test_report_is_json_serializable():
    r = score(FULL, GOLD, matcher=substr_matcher, java_verifier=OkVerifier())
    blob = json.dumps(r.as_dict(), ensure_ascii=False)
    assert '"score": 1.0' in blob and '"javaVerifier": true' in blob


def test_rejects_non_string_answer():
    with pytest.raises(TypeError):
        score(None, GOLD, matcher=substr_matcher)  # type: ignore[arg-type]


def test_empty_gold_scores_zero():
    r = score("随便说说", {}, matcher=substr_matcher)
    assert r.coverage == 0.0 and r.score == 0.0 and r.blocked is False


def test_score_many_returns_one_report_per_pair():
    reports = score_many([(FULL, GOLD), ("", GOLD)], matcher=substr_matcher)
    assert [x.score for x in reports] == [1.0, 0.0]
