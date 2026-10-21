"""D-F2 基线运行入口：一条命令跑完 evolution 集，输出逐例记录与 RunReport。

用法（在仓库根目录）
  python benchmark/run_benchmark.py --manifest benchmark/manifests/baseline-v0.json
  python benchmark/run_benchmark.py --manifest ... --plan          只列用例，不连服务
  python benchmark/run_benchmark.py --manifest ... --base-url http://127.0.0.1:8000 \
      --gold-root ../restricted/gold --out runs/benchmark/baseline-v0

退出码
  0  全部 PASS（或 --plan 模式）
  1  存在 DEGRADED / FAIL / BLOCKED
  2  manifest 不符合 contracts 的 RunManifest，或参数不成立
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "benchmark"))

from runner import (
    PASS,
    BenchmarkRunner,
    HttpTransport,
    load_manifest_schema,
    validate_manifest,
)


def default_gold_root() -> Path:
    env = os.environ.get("COURSEPILOT_GOLD_ROOT")
    if env:
        return Path(env)
    return REPO_ROOT.parent / "restricted" / "gold"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="D 模块基准运行入口（D-F2 基线）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="C 侧 planning 服务地址")
    parser.add_argument("--cases-root", default=str(REPO_ROOT / "benchmark" / "cases" / "evolution"))
    parser.add_argument("--gold-root", default=str(default_gold_root()))
    parser.add_argument("--manifest", required=True, help="RunManifest JSON 路径（字段以 contracts 为准）")
    parser.add_argument("--out", default=None, help="输出目录，默认 runs/benchmark/<runId>")
    parser.add_argument("--mode", default="SIMULATION", choices=("SIMULATION", "REAL"))
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--plan", action="store_true", help="只列用例与判定计划，不连服务")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        print(f"找不到 manifest：{manifest_path}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems = validate_manifest(manifest, load_manifest_schema(REPO_ROOT / "contracts"))
    if problems:
        print("manifest 不符合 contracts 的 RunManifest：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    runner = BenchmarkRunner(
        HttpTransport(args.base_url, timeout=args.timeout),
        cases_root=Path(args.cases_root),
        gold_root=Path(args.gold_root),
        contracts_root=REPO_ROOT / "contracts",
        mode=args.mode,
    )
    result = runner.run(manifest, repo_root=REPO_ROOT, plan_only=args.plan)

    out_dir = Path(args.out) if args.out else REPO_ROOT / "runs" / "benchmark" / str(manifest["runId"])
    paths = runner.write_outputs(result, out_dir)

    summary = result["summary"]
    print(f"{'用例':<10}{'组':<5}{'判定':<10}说明")
    print("-" * 78)
    for outcome in result["outcomes"]:
        note = outcome.error or ", ".join(outcome.placeholders) or ", ".join(outcome.notes[:1]) or ""
        print(f"{outcome.case_id:<10}{outcome.group_id:<5}{outcome.status:<10}{note[:44]}")
    print("-" * 78)
    print(f"用例数 {summary['caseCount']}，判定分布 {summary['statusCounts']}")
    print(f"分组均值 {summary['groupMeans']}，宏平均 {summary['macroScore']}")
    if not summary["macroComparable"]:
        print(
            f"  注意：只有 {summary['scoredGroups']} 有分数（用例共 {summary['caseGroups']} 组），"
            "宏平均不能当四组等权结果读"
        )
    print(f"成本覆盖率 {summary['costCoverage']}（None 表示 Provider 未给用量，不按 0 计）")
    print(f"输出目录 {out_dir}")
    for name, path in paths.items():
        print(f"  {name}: {path}")

    if args.plan:
        return 0
    bad = [outcome for outcome in result["outcomes"] if outcome.status != PASS]
    if bad:
        print(f"\n{len(bad)} 例未通过（{', '.join(sorted({item.status for item in bad}))}）", file=sys.stderr)
        return 1
    print("\n全部 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
