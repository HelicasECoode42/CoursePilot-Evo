"""分层判定的正反例：满分答案要接近 1.0，明显错的答案要 0 且说清哪条没中。

不测模型、不连服务：只钉住「哪类判据按什么判、判不中怎么记、文本判占比怎么报」。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from scoring.judge import MODE_STRUCTURED, MODE_TEXT, MODE_UNWIRED, judge

GOLD = {
    "caseId": "GX-001",
    "requiredFacts": ["通识课第 2-3 学期总计要求 4 学分"],
    "requiredUnknowns": ["全英语授课课程要求是否已满足无法判断"],
    "requiredClarification": ["请提供该课成绩是否合格"],
    "forbiddenClaims": ["不得声称全英语授课课程要求已满足"],
    "requiredSourceRefs": [{"refId": "cs2024-s1-A49"}],
}


def perfect_answer() -> dict:
    return {
        "decision": "RECOMMENDATIONS",
        "recommendations": [{"courseCode": "CS1", "courseName": "通识课第 2-3 学期总计要求 4 学分"}],
        "clarification": {"questionId": "grade:missing", "text": "请提供该课成绩是否合格"},
        "unknowns": [{"code": "UNKNOWN_RULE", "message": "全英语授课课程要求是否已满足无法判断"}],
    }


class FakeVerifier:
    def __init__(self, problem=None):
        self.problem = problem
        self.calls = []

    def verify_source_ref(self, ref):
        self.calls.append(ref.get("refId"))
        return self.problem


def answer_text_of(data: dict) -> str:
    parts = []
    for item in data.get("recommendations") or []:
        parts.append(" ".join(str(item.get(key) or "") for key in ("courseCode", "courseName", "reason")))
    clarification = data.get("clarification") or {}
    parts.append(str(clarification.get("text") or ""))
    for unknown in data.get("unknowns") or []:
        parts.append(str(unknown.get("message") or ""))
    parts.append(f"结论 {data.get('decision') or ''}")
    return "\n".join(part for part in parts if part.strip())


def test_perfect_answer_scores_full() -> None:
    data = perfect_answer()
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    assert report.score == 1.0
    assert report.blocked is False
    assert report.coverage == 1.0


def test_structured_modes_are_used_for_unknown_and_clarification() -> None:
    data = perfect_answer()
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    modes = {verdict.kind: verdict.mode for verdict in report.verdicts}
    assert modes["requiredUnknowns"] == MODE_STRUCTURED
    assert modes["requiredClarification"] == MODE_STRUCTURED
    assert modes["requiredFacts"] == MODE_TEXT
    assert modes["forbiddenClaims"] == MODE_TEXT


def test_wrong_answer_scores_zero_and_says_which_claim_missed() -> None:
    data = {
        "decision": "RECOMMENDATIONS",
        "recommendations": [{"courseCode": "CS9", "courseName": "别的一门课", "reason": "随便选的"}],
        "clarification": None,
        "unknowns": [],
    }
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    assert report.score == 0.0
    assert report.blocked is False
    missed = [verdict for verdict in report.verdicts if not verdict.matched and verdict.kind != "forbiddenClaims"]
    assert len(missed) == 3
    assert any("澄清" in verdict.note for verdict in missed)
    assert any("unknowns" in verdict.note for verdict in missed)


def test_forbidden_claim_blocks_the_whole_case() -> None:
    data = perfect_answer()
    data["recommendations"].append({"courseName": "全英语授课课程要求已满足"})
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    assert report.blocked is True
    assert report.score == 0.0


def test_uncertain_wording_is_not_a_violation() -> None:
    """判据写「不得声称…已满足」，而正确答案会以「是否满足无法判断」提及同一串词，不能判成违规。"""
    data = perfect_answer()
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    forbidden = next(v for v in report.verdicts if v.kind == "forbiddenClaims")
    assert forbidden.matched is False
    assert "不确定" in forbidden.note or forbidden.note == ""


def test_asserting_the_forbidden_claim_in_plain_words_is_a_violation() -> None:
    data = perfect_answer()
    data["recommendations"].append({"courseName": "全英语授课课程要求未满足"})
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    assert report.blocked is True


def test_clarification_that_asks_the_wrong_thing_does_not_count() -> None:
    data = perfect_answer()
    data["clarification"] = {"questionId": "x", "text": "你希望什么时候上课"}
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    verdict = next(v for v in report.verdicts if v.kind == "requiredClarification")
    assert verdict.matched is False
    assert "不一致" in verdict.note


def test_unwired_java_verifier_is_counted_not_passed() -> None:
    data = perfect_answer()
    report = judge(data, GOLD, answer=answer_text_of(data))
    assert report.refs[0].status == "unverified"
    assert report.mode_counts()[MODE_UNWIRED] == 1
    assert report.blocked is False


def test_failed_reference_blocks() -> None:
    data = perfect_answer()
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier("引用不存在"))
    assert report.refs[0].status == "failed"
    assert report.blocked is True
    assert report.score == 0.0


def test_mode_counts_and_text_share_are_reported() -> None:
    data = perfect_answer()
    report = judge(data, GOLD, answer=answer_text_of(data), java_verifier=FakeVerifier())
    counts = report.mode_counts()
    assert counts[MODE_STRUCTURED] == 2
    assert counts[MODE_TEXT] == 2
    assert counts[MODE_UNWIRED] == 0
    assert report.text_share() == 0.5
    assert report.as_dict()["textShare"] == 0.5


# -- 用真实判据做验收：把 gold 的五栏都答到的构造答案应接近满分 ------------------
REAL_GOLD = ROOT.parent / "restricted" / "gold" / "G2-001.json"


@pytest.mark.skipif(not REAL_GOLD.is_file(), reason="判据在工作区外，仅在本地复核环境跑")
def test_real_gold_perfect_answer_is_near_full() -> None:
    import json

    gold = json.loads(REAL_GOLD.read_text(encoding="utf-8"))
    data = {
        "decision": "RECOMMENDATIONS",
        "recommendations": [{"courseName": " ".join(gold.get("requiredFacts") or [])}],
        "clarification": {"questionId": "demo", "text": " ".join(gold.get("requiredClarification") or [])},
        "unknowns": [{"code": "UNKNOWN", "message": message} for message in (gold.get("requiredUnknowns") or [])],
    }
    report = judge(data, gold, answer=answer_text_of(data))
    assert report.score >= 0.9, report.as_dict()
    assert report.blocked is False
    assert report.refs[0].status == "unverified"


@pytest.mark.skipif(not REAL_GOLD.is_file(), reason="判据在工作区外，仅在本地复核环境跑")
def test_real_gold_empty_answer_scores_zero() -> None:
    import json

    gold = json.loads(REAL_GOLD.read_text(encoding="utf-8"))
    report = judge({"decision": "RECOMMENDATIONS", "recommendations": [], "unknowns": []}, gold, answer="")
    assert report.score == 0.0
    assert report.blocked is False
