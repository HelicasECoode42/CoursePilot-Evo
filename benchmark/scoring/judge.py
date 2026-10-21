"""分层判定：能结构化的判据用结构化字段判，判不了的才退回全文匹配。

为什么要有这一层
  keyword_matcher 拿判据原句跟「把整份答案拼成的一段文本」算关键词覆盖率。答案一换措辞分数就掉，
  于是出现「链路通、判据全中、分数 0.0」这种没法解释的结果。判据里其实有两类是结构化的：
  「必须答到的未知」对答案的 unknowns，「必须反问」对答案的 clarification。
  这两类按字段判，只剩「必须答到的事实」和「不许说的结论」需要文本判。

分层口径
  structured  必须未知 → 答案 unknowns 里任一条的 code+message 与判据句重叠达到阈值
              必须反问 → 答案 clarification 存在，且其 text 与判据句重叠达到阈值
  text        必须答到的事实 → 全文匹配（默认 keyword_matcher 占位基线）
              不许说的结论   → 全文匹配，命中即整题 blocked
  unwired     引用核验 → 没有 JavaVerifier 时记 unwired，既不算通过也不判 blocked

报告必须写清各层条数：文本判占比越高，这份分数越不能当语义正确率读。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from scoring.scorer import keyword_matcher

STRUCTURED_THRESHOLD = 0.5

#: 「说的是不确定」而不是「下了结论」的标记词。判「不许说的结论」时，这类句子不算命中，
#: 否则正确回答「全英语要求是否满足无法判断」会被判成「声称已满足」。
#: 注意只收不确定性措辞：「未满足」「不满足」是断言，仍算命中。
_UNCERTAIN = re.compile(r"无法判断|无法确定|不确定|未知|不能判断|是否|待确认|未提供|缺少|未核验|不可确认")

_SENTENCE_SPLIT = re.compile(r"[。\n;；!！?？]")

MODE_STRUCTURED = "structured"
MODE_TEXT = "text"
MODE_UNWIRED = "unwired"

_GRADED_KINDS = ("requiredFacts", "requiredUnknowns", "requiredClarification")


class Matcher(Protocol):
    def __call__(self, claim: str, answer: str) -> bool: ...


class JavaVerifier(Protocol):
    def verify_source_ref(self, ref: dict[str, Any]) -> str | None: ...


def _tokens(text: str) -> list[str]:
    """粗切关键词元：ASCII 词元 + 中文二元组。与 scorer 的口径一致，但不 import 它的私有函数。"""
    out: list[str] = []
    for match in re.finditer(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()):
        piece = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", piece):
            out += [piece[i : i + 2] for i in range(len(piece) - 1)] or [piece]
        else:
            out.append(piece)
    return out


def overlap(claim: str, candidate: str, *, threshold: float = STRUCTURED_THRESHOLD) -> bool:
    tokens = _tokens(claim)
    if not tokens or not candidate:
        return False
    hits = sum(1 for token in tokens if token in candidate.lower())
    return hits / len(tokens) >= threshold


def forbidden_hit(claim: str, answer: str, matcher: Matcher) -> tuple[bool, str]:
    """判「不许说的结论」是否被违反。

    先整段匹配，再看出现在哪些句子：如果所有命中句都是否定式提及（说未知、说不得），
    不算违反。这是启发式：真正的违规句通常在同一段里以肯定语气出现，会被单独命中。
    """
    if not matcher(claim, answer):
        return False, ""
    sentences = [item.strip() for item in _SENTENCE_SPLIT.split(answer) if item.strip()]
    hits = [sentence for sentence in sentences if overlap(claim, sentence, threshold=0.6)]
    if hits and all(_UNCERTAIN.search(sentence) for sentence in hits):
        return False, "命中句说的是「不确定」（说未知/是否），不计命中"
    return True, "命中即整题不给分"


@dataclass
class ClaimVerdict:
    kind: str
    index: int
    text: str
    matched: bool
    mode: str
    note: str = ""


@dataclass
class RefVerdict:
    index: int
    ref_id: str
    status: str  # verified / failed / unverified
    note: str = ""


@dataclass
class JudgeReport:
    case_id: str
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    refs: list[RefVerdict] = field(default_factory=list)
    matcher_name: str = "keyword_matcher"
    java_verifier: bool = False

    @property
    def blocked(self) -> bool:
        if any(v.matched for v in self.verdicts if v.kind == "forbiddenClaims"):
            return True
        return any(r.status == "failed" for r in self.refs)

    @property
    def coverage(self) -> float:
        graded = [v for v in self.verdicts if v.kind != "forbiddenClaims"]
        if not graded:
            return 0.0
        return sum(1 for v in graded if v.matched) / len(graded)

    @property
    def score(self) -> float:
        return 0.0 if self.blocked else round(self.coverage, 4)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for verdict in self.verdicts:
            out[verdict.kind] = out.get(verdict.kind, 0) + 1
        return out

    def mode_counts(self) -> dict[str, int]:
        out = {MODE_STRUCTURED: 0, MODE_TEXT: 0, MODE_UNWIRED: 0}
        for verdict in self.verdicts:
            out[verdict.mode] = out.get(verdict.mode, 0) + 1
        for ref in self.refs:
            if ref.status == "unverified":
                out[MODE_UNWIRED] += 1
        return out

    def text_share(self) -> float:
        counts = self.mode_counts()
        judged = counts[MODE_STRUCTURED] + counts[MODE_TEXT] + counts[MODE_UNWIRED]
        return round(counts[MODE_TEXT] / judged, 4) if judged else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "score": self.score,
            "blocked": self.blocked,
            "coverage": round(self.coverage, 4),
            "counts": self.counts(),
            "modeCounts": self.mode_counts(),
            "textShare": self.text_share(),
            "matcher": self.matcher_name,
            "javaVerifier": self.java_verifier,
            "verdicts": [vars(verdict) for verdict in self.verdicts],
            "sourceRefs": [vars(ref) for ref in self.refs],
        }


def _unknown_candidates(data: dict[str, Any]) -> list[str]:
    holders = [data, data.get("academicAudit") or {}]
    out: list[str] = []
    for holder in holders:
        for unknown in holder.get("unknowns") or []:
            out.append(f"{unknown.get('code') or ''} {unknown.get('message') or ''}".strip())
    return [item for item in out if item]


def _clarification_text(data: dict[str, Any]) -> str:
    clarification = data.get("clarification") or {}
    return str(clarification.get("text") or "")


def judge(
    data: dict[str, Any],
    gold: dict[str, Any],
    *,
    answer: str,
    matcher: Matcher | None = None,
    java_verifier: JavaVerifier | None = None,
) -> JudgeReport:
    """按判据给一份结构化答复打分：结构化字段优先，判不了的才退回文本。"""
    text_matcher: Matcher = matcher or keyword_matcher
    report = JudgeReport(
        case_id=str(gold.get("caseId", "")),
        matcher_name=getattr(text_matcher, "__name__", type(text_matcher).__name__),
        java_verifier=java_verifier is not None,
    )
    unknown_candidates = _unknown_candidates(data)
    clarification = _clarification_text(data)

    for kind in _GRADED_KINDS:
        for index, claim in enumerate(gold.get(kind) or [], 1):
            if kind == "requiredUnknowns":
                hit = any(overlap(claim, candidate) for candidate in unknown_candidates)
                mode = MODE_STRUCTURED
                note = "" if hit else "答案的 unknowns 里没有与之对应的条目"
            elif kind == "requiredClarification":
                hit = bool(clarification) and overlap(claim, clarification)
                mode = MODE_STRUCTURED
                if not clarification:
                    note = "答案没有澄清问题"
                else:
                    note = "" if hit else "澄清内容与判据要求的缺项不一致"
            else:
                hit = bool(text_matcher(claim, answer))
                mode = MODE_TEXT
                note = "" if hit else "文本匹配未命中"
            report.verdicts.append(ClaimVerdict(kind, index, claim, hit, mode, note))

    for index, claim in enumerate(gold.get("forbiddenClaims") or [], 1):
        hit, note = forbidden_hit(claim, answer, text_matcher)
        report.verdicts.append(ClaimVerdict("forbiddenClaims", index, claim, hit, MODE_TEXT, note))

    for index, ref in enumerate(gold.get("requiredSourceRefs") or [], 1):
        ref_id = str(ref.get("refId", ""))
        if java_verifier is None:
            report.refs.append(RefVerdict(index, ref_id, "unverified", "JavaVerifier 未接线"))
            continue
        problem = java_verifier.verify_source_ref(ref)
        report.refs.append(RefVerdict(index, ref_id, "failed" if problem else "verified", problem or ""))
    return report
