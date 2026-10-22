"""D-F4 失败归因骨架：把逐例失败整理成可复核的假设。

协议口径（docs/07 第 4 节）
  Failure Miner 只看训练侧的逐例结果与 Trace，把多例相同失败整理成
  `hypothesisId, caseIds>=2, pattern, likelyCause, proposedPatch, expectedMetric`；
  **单例失误不得触发自动 patch**。候选只能修改 Harness 白名单内的文件。

两条硬规则
  1 少于两个不同 case 的失败不成为假设，但要留在 rejected 里并写明原因，不能悄悄丢掉；
  2 环境未接线的用例（BLOCKED / 带 FAKE_* 的 DEGRADED）不参与归因——把它们算成模型失败，
     等于把「没接线」写成「表现差」。这类只计入 excluded 并标明原因。

本模块只做归因，不生成补丁、不判断晋级；Evolver 与 PromotionGate 在第六周另行实现。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIN_CASES = 2

#: 协议允许候选修改的文件（agent-runtime/harness 白名单）。归因产出的 allowedTargets 必须落在这里面。
HARNESS_WHITELIST = (
    "agent-runtime/harness/AGENTS.md",
    "agent-runtime/harness/skills/",
    "agent-runtime/harness/tool_policy.yaml",
    "agent-runtime/harness/context_policy.yaml",
)

#: 判据种类 → 失败类别 → 可改的白名单落点（写死对照，避免归因结果指向不该改的地方）。
CATEGORY_RULES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "requiredFactMissed": ("事实覆盖", ("agent-runtime/harness/skills/",), "task score 上升且无新增禁止结论"),
    "requiredUnknownMissed": (
        "未知与澄清",
        ("agent-runtime/harness/AGENTS.md", "agent-runtime/harness/skills/"),
        "unknown 命中率上升，过度拒答不增加",
    ),
    "requiredClarificationMissed": (
        "未知与澄清",
        ("agent-runtime/harness/skills/", "agent-runtime/harness/tool_policy.yaml"),
        "clarification correctness 上升，不需澄清时不无故阻塞",
    ),
    "forbiddenClaimHit": (
        "无依据主张",
        ("agent-runtime/harness/context_policy.yaml",),
        "unsupported claim 归零，task score 不下降",
    ),
}

KIND_LABEL = {
    "requiredFacts": "requiredFactMissed",
    "requiredUnknowns": "requiredUnknownMissed",
    "requiredClarification": "requiredClarificationMissed",
    "forbiddenClaims": "forbiddenClaimHit",
}


@dataclass
class FailureRecord:
    case_id: str
    group_id: str
    status: str
    kind: str
    claim: str
    note: str = ""

    @property
    def signature(self) -> tuple[str, str]:
        return (self.kind, self.claim.strip())


@dataclass
class Hypothesis:
    hypothesis_id: str
    category: str
    case_ids: list[str]
    pattern: str
    likely_cause: str
    allowed_targets: list[str]
    expected_metric: str
    trace_refs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "hypothesisId": self.hypothesis_id,
            "category": self.category,
            "caseIds": self.case_ids,
            "pattern": self.pattern,
            "likelyCause": self.likely_cause,
            "allowedTargets": self.allowed_targets,
            "expectedMetric": self.expected_metric,
            "traceRefs": self.trace_refs,
            "notes": self.notes,
        }


def _hypothesis_id(signature: tuple[str, str]) -> str:
    digest = hashlib.sha256(f"{signature[0]}|{signature[1]}".encode()).hexdigest()[:12]
    return f"hyp-{digest}"


def is_environment_gap(case: dict[str, Any]) -> str | None:
    """判断一条用例是否属于「环境未接线」，返回原因文本或 None。"""
    status = str(case.get("status") or "")
    if status == "BLOCKED":
        return f"未取得有效结果：{case.get('error') or '上游不可用'}"
    placeholders = case.get("placeholders") or []
    if placeholders:
        return f"答案带占位标记 {', '.join(placeholders)}：环境未接线，不能算模型失败"
    return None


def collect_failures(cases: Iterable[dict[str, Any]]) -> tuple[list[FailureRecord], list[dict[str, Any]]]:
    """从逐例记录里抽出失败项。返回 (失败项, 排除项)。"""
    records: list[FailureRecord] = []
    excluded: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("caseId") or "unknown")
        group_id = str(case.get("groupId") or "unknown")
        gap = is_environment_gap(case)
        if gap:
            excluded.append({"caseId": case_id, "reason": gap})
            continue
        report = case.get("scoreReport") or {}
        for verdict in report.get("verdicts") or []:
            kind = verdict.get("kind")
            if kind not in KIND_LABEL:
                continue
            matched = bool(verdict.get("matched"))
            failed = matched if kind == "forbiddenClaims" else not matched
            if not failed:
                continue
            records.append(
                FailureRecord(
                    case_id=case_id,
                    group_id=group_id,
                    status=str(case.get("status") or ""),
                    kind=KIND_LABEL[kind],
                    claim=str(verdict.get("text") or ""),
                    note=str(verdict.get("note") or ""),
                )
            )
    return records, excluded


class FailureMiner:
    """按签名归并失败，产出假设；单例进 rejected，并保留原因。"""

    def mine(self, cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
        case_list = list(cases)
        records, excluded = collect_failures(case_list)
        buckets: dict[tuple[str, str], list[FailureRecord]] = {}
        for record in records:
            buckets.setdefault(record.signature, []).append(record)

        hypotheses: list[Hypothesis] = []
        rejected: list[dict[str, Any]] = []
        for signature, items in sorted(buckets.items(), key=lambda item: item[0]):
            case_ids = sorted({item.case_id for item in items})
            kind, claim = signature
            if len(case_ids) < MIN_CASES:
                rejected.append(
                    {
                        "kind": kind,
                        "claim": claim,
                        "caseIds": case_ids,
                        "reason": f"仅 {len(case_ids)} 例，低于门槛 {MIN_CASES}：单例失误不得触发自动补丁",
                    }
                )
                continue
            category, targets, expected = CATEGORY_RULES[kind]
            for target in targets:
                if target not in HARNESS_WHITELIST:
                    raise ValueError(f"归因结果指向白名单外的路径：{target}")
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=_hypothesis_id(signature),
                    category=category,
                    case_ids=case_ids,
                    pattern=f"{kind}：{claim}",
                    likely_cause=self._likely_cause(kind, len(case_ids)),
                    allowed_targets=list(targets),
                    expected_metric=expected,
                    trace_refs=sorted({item.note for item in items if item.note}),
                    notes=[f"涉及 {len(items)} 条失败记录、{len(case_ids)} 个不同用例"],
                )
            )
        return {
            "hypotheses": [hypothesis.as_dict() for hypothesis in hypotheses],
            "rejected": rejected,
            "excluded": excluded,
            "summary": {
                "caseCount": len(case_list),
                "failureRecords": len(records),
                "hypothesisCount": len(hypotheses),
                "rejectedCount": len(rejected),
                "excludedCount": len(excluded),
                "minCases": MIN_CASES,
                "note": "只做归因：不生成补丁、不判断晋级；Evolver 与 PromotionGate 属第六周",
            },
        }

    @staticmethod
    def _likely_cause(kind: str, distinct_cases: int) -> str:
        """给出可讨论的成因假设，不写成结论——成因要靠人复核。"""
        base = {
            "requiredFactMissed": "答案没有覆盖判据要求的事实，可能是检索到的依据未进入上下文或回答未汇总依据",
            "requiredUnknownMissed": "缺资料时没有声明未知，可能把「语料没有」读成了「确定没有」",
            "requiredClarificationMissed": "关键缺项没有被反问，可能澄清策略覆盖的条件不全",
            "forbiddenClaimHit": "出现了判据禁止的主张，可能需要收紧上下文策略中的断言口径",
        }[kind]
        return f"{base}（{distinct_cases} 个不同用例重复出现）"


def mine_file(cases_path: Path) -> dict[str, Any]:
    """读 `cases.jsonl` 并归因，供命令行入口使用。"""
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return FailureMiner().mine(cases)
