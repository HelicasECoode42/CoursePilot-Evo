#!/usr/bin/env python3
"""评分器骨架：把判据五栏折算成分数。规则显式、可复算、不依赖模型。

分工
  D 定义评分规则与判据结构；语义匹配由调用方注入的 matcher 提供（C 的唯一 Runner 接线）；
  引用的事实验证由 JavaVerifier 注入（B 模块的 Verifier，经 typed HTTP 调用）。

五栏计分口径
  requiredFacts / requiredUnknowns / requiredClarification   各栏等权，命中一条得一分
  forbiddenClaims                                            命中任一条即整题 blocked，分数归零
  requiredSourceRefs                                         交 JavaVerifier 逐条核验；核不过即 blocked

blocked 的含义与 docs/07 的「unsupported claim 为零」一致：出现禁止结论或引用不存在的事实，
本题不给分，并把失败分支原样留下，供 Failure Miner 归因。不强行宣称成功。

未接线的部分
  C 的 Runner 未就绪时 matcher 用本模块的 keyword_matcher（关键词元覆盖率的占位基线），
  JavaVerifier 传 None（引用记为 unverified，不计分也不判 blocked）。这两处都显式记进报告，
  避免把「未核验」读成「已通过」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

FACT_COVERAGE_THRESHOLD = 0.6


class Matcher(Protocol):
    def __call__(self, claim: str, answer: str) -> bool: ...


class JavaVerifier(Protocol):
    def verify_source_ref(self, ref: dict[str, Any]) -> str | None:
        """返回 None 表示核验通过；返回问题说明表示不通过。"""
        ...


def _tokens(text: str) -> list[str]:
    """粗切关键词元：ASCII 词元 + 中文二元组。不引入分词依赖，保证可复算。"""
    out: list[str] = []
    for m in re.finditer(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()):
        s = m.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", s):
            out += [s[i : i + 2] for i in range(len(s) - 1)] or [s]
        else:
            out.append(s)
    return out


def keyword_matcher(claim: str, answer: str, *, threshold: float = FACT_COVERAGE_THRESHOLD) -> bool:
    """占位基线：判据句子切成词元，answer 覆盖比例达到 threshold 即算命中。

    仅用于没有 Runner 时的自测与回归；语义等价、否定、反问等情形它判不出来，
    接线后应替换为 Runner 提供的匹配器。
    """
    toks = _tokens(claim)
    if not toks:
        return False
    hits = sum(1 for t in toks if t in answer.lower())
    return hits / len(toks) >= threshold


@dataclass
class Verdict:
    kind: str
    index: int
    text: str
    matched: bool
    note: str = ""


@dataclass
class RefVerdict:
    index: int
    ref_id: str
    status: str  # verified / failed / unverified
    note: str = ""


@dataclass
class ScoreReport:
    case_id: str
    verdicts: list[Verdict] = field(default_factory=list)
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
        for v in self.verdicts:
            out[v.kind] = out.get(v.kind, 0) + 1
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "score": self.score,
            "blocked": self.blocked,
            "coverage": round(self.coverage, 4),
            "counts": self.counts(),
            "matcher": self.matcher_name,
            "javaVerifier": self.java_verifier,
            "verdicts": [vars(v) for v in self.verdicts],
            "sourceRefs": [vars(r) for r in self.refs],
        }


_GRADED_KINDS = ("requiredFacts", "requiredUnknowns", "requiredClarification")


def score(
    answer: str, gold: dict[str, Any], *, matcher: Matcher | None = None, java_verifier: JavaVerifier | None = None
) -> ScoreReport:
    """按判据给一份答案打分。answer 为自然语言回答；gold 为判据对象。"""
    if not isinstance(answer, str):
        raise TypeError("answer must be str")
    m: Matcher = matcher or keyword_matcher
    report = ScoreReport(
        case_id=str(gold.get("caseId", "")),
        matcher_name=getattr(m, "__name__", type(m).__name__),
        java_verifier=java_verifier is not None,
    )

    for kind in _GRADED_KINDS:
        for i, claim in enumerate(gold.get(kind) or [], 1):
            report.verdicts.append(Verdict(kind, i, claim, bool(m(claim, answer))))

    for i, claim in enumerate(gold.get("forbiddenClaims") or [], 1):
        hit = bool(m(claim, answer))
        report.verdicts.append(Verdict("forbiddenClaims", i, claim, hit, "命中即整题不给分" if hit else ""))

    for i, ref in enumerate(gold.get("requiredSourceRefs") or [], 1):
        ref_id = str(ref.get("refId", ""))
        if java_verifier is None:
            report.refs.append(RefVerdict(i, ref_id, "unverified", "JavaVerifier 未接线"))
            continue
        problem = java_verifier.verify_source_ref(ref)
        report.refs.append(RefVerdict(i, ref_id, "failed" if problem else "verified", problem or ""))
    return report


def score_many(
    pairs, *, matcher: Matcher | None = None, java_verifier: JavaVerifier | None = None
) -> list[ScoreReport]:
    """pairs 为 (answer, gold) 序列。跨 case 的失败归因在 Runner 侧做，本函数只逐条算分。"""
    return [score(a, g, matcher=matcher, java_verifier=java_verifier) for a, g in pairs]
