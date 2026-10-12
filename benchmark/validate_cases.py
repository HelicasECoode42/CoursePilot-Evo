#!/usr/bin/env python3
"""D1 案例校验器：题面（可公开）与标注（私有）分开校验。

用途
  * 判据字段齐备、格式正确，不需要人眼看；
  * 题面文件里不得出现任何判据字段（答案泄漏检查）；
  * 来源引用必须落在题面声明的快照上，且结构符合 contracts 的 SourceRef。

用法
  python benchmark/validate_cases.py
  python benchmark/validate_cases.py --cases-root benchmark/cases/evolution \
      --gold-root ../restricted/gold
  gold-root 默认取环境变量 COURSEPILOT_GOLD_ROOT，未设置时为 <repo 上一级>/restricted/gold。
  退出码：有 ERROR 为 1，只有 WARNING 或全通过为 0。

错误码
  E01 题面不符合 CasePrompt  E02 标注文件缺失  E03 标注不符合 CaseGold
  E04 caseId 不一致          E05 split 与目录不符  E06 题面含判据字段（答案泄漏）
  E07 引用的快照与题面不一致   E08 引用不符合契约 SourceRef  E09 判据字段空项或重复
  E10 复核人不足两人          E11 输入 fixture 文件不存在
警告码
  W01 status=needs_review（应排除出评测）  W02 status=draft（尚未完成双人复核）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts" / "schemas" / "domain.schema.json"
CASE_SCHEMA = ROOT / "benchmark" / "schemas" / "case.schema.json"

GOLD_ONLY_FIELDS = (
    "requiredFacts",
    "requiredUnknowns",
    "requiredClarification",
    "forbiddenClaims",
    "requiredSourceRefs",
)


def load_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def source_ref_validator() -> Draft202012Validator:
    """SourceRef 结构复用契约里的定义，本模块不另立一套。"""
    contract = load_json(CONTRACTS)
    return Draft202012Validator(contract["$defs"]["SourceRef"])


def case_validators():
    schema = load_json(CASE_SCHEMA)
    return (
        Draft202012Validator(schema["$defs"]["CasePrompt"]),
        Draft202012Validator(schema["$defs"]["CaseGold"]),
    )


def validate_one(prompt_path: Path, gold_root: Path, v_prompt, v_gold, v_ref):
    errors, warnings = [], []
    raw = load_json(prompt_path)
    case_id = raw.get("caseId", prompt_path.stem)

    for e in v_prompt.iter_errors(raw):
        errors.append(("E01", f"{case_id} 题面不合规：{list(e.path)} {e.message}"))

    leaked = [f for f in GOLD_ONLY_FIELDS if f in raw]
    if leaked:
        errors.append(("E06", f"{case_id} 题面文件含判据字段 {leaked}，答案会随题面公开"))

    fixture = ROOT / str(raw.get("inputFixtureRef", ""))
    if raw.get("inputFixtureRef") and not fixture.is_file():
        errors.append(("E11", f"{case_id} 输入 fixture 不存在：{raw['inputFixtureRef']}"))

    if prompt_path.parent.name != raw.get("split"):
        errors.append(("E05", f"{case_id} split={raw.get('split')} 与目录 {prompt_path.parent.name} 不符"))

    gold_path = gold_root / f"{case_id}.json"
    if not gold_path.is_file():
        errors.append(("E02", f"{case_id} 缺标注文件 {gold_path}"))
        return case_id, raw, None, errors, warnings

    gold = load_json(gold_path)
    for e in v_gold.iter_errors(gold):
        errors.append(("E03", f"{case_id} 标注不合规：{list(e.path)} {e.message}"))

    if gold.get("caseId") != case_id:
        errors.append(("E04", f"{case_id} 标注 caseId={gold.get('caseId')} 不一致"))

    for name in ("requiredFacts", "requiredUnknowns", "requiredClarification", "forbiddenClaims"):
        items = gold.get(name) or []
        if any(not str(x).strip() for x in items):
            errors.append(("E09", f"{case_id} {name} 有空项"))
        if len(items) != len(set(items)):
            errors.append(("E09", f"{case_id} {name} 有重复条目"))
        if name == "requiredFacts" and not items:
            errors.append(("E09", f"{case_id} requiredFacts 为空，案例没有可确认事实"))

    refs = gold.get("requiredSourceRefs") or []
    for ref in refs:
        for e in v_ref.iter_errors(ref):
            errors.append(("E08", f"{case_id} 引用 {ref.get('refId')} 不符 SourceRef：{e.message}"))
        if ref.get("kind") == "CURRICULUM" and ref.get("snapshotId") != raw.get("curriculumSnapshotId"):
            errors.append(
                (
                    "E07",
                    f"{case_id} 引用 {ref.get('refId')} 快照={ref.get('snapshotId')} 与题面 {raw.get('curriculumSnapshotId')} 不一致",
                )
            )

    reviewers = gold.get("reviewerIds") or []
    if len(set(reviewers)) < 2:
        errors.append(("E10", f"{case_id} 复核人不足两人：{reviewers}"))

    status = gold.get("status")
    if status == "needs_review":
        warnings.append(("W01", f"{case_id} 存在标注分歧，应排除出评测"))
    elif status == "draft":
        warnings.append(("W02", f"{case_id} 尚未完成双人复核"))

    return case_id, raw, gold, errors, warnings


def validate_collection(cases_root: Path, gold_root: Path):
    v_prompt, v_gold = case_validators()
    v_ref = source_ref_validator()
    results, errors, warnings = [], [], []
    for path in sorted(cases_root.glob("*.json")):
        if path.name == "README.md":
            continue
        cid, raw, gold, errs, warns = validate_one(path, gold_root, v_prompt, v_gold, v_ref)
        results.append(
            {
                "caseId": cid,
                "groupId": raw.get("groupId"),
                "split": raw.get("split"),
                "status": (gold or {}).get("status"),
            }
        )
        errors += errs
        warnings += warns
    return results, errors, warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="校验 benchmark 案例的题面与标注")
    ap.add_argument("--cases-root", default=str(ROOT / "benchmark" / "cases" / "evolution"))
    ap.add_argument(
        "--gold-root", default=os.environ.get("COURSEPILOT_GOLD_ROOT", str(ROOT.parent / "restricted" / "gold"))
    )
    args = ap.parse_args(argv)

    cases_root, gold_root = Path(args.cases_root), Path(args.gold_root)
    if not cases_root.is_dir():
        print(f"题面目录不存在：{cases_root}")
        return 1

    results, errors, warnings = validate_collection(cases_root, gold_root)
    print(f"题面目录：{cases_root}")
    print(f"标注目录：{gold_root}")
    for r in results:
        print(f"  [{r['status'] or '-':>12}] {r['caseId']} {r['groupId']}/{r['split']}")
    for code, msg in warnings:
        print(f"  WARN {code} {msg}")
    for code, msg in errors:
        print(f"  ERR  {code} {msg}")
    print(f"\n共 {len(results)} 条案例；ERROR {len(errors)}，WARNING {len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
