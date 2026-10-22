"""D-F4 归因入口：读一次运行的 cases.jsonl，产出假设、被拒单例与环境未接线清单。

用法（在仓库根目录）
  python benchmark/mine_failures.py --run runs/benchmark/baseline-v0
  python benchmark/mine_failures.py --run runs/benchmark/baseline-v0 --out runs/benchmark/baseline-v0/hypotheses.json

退出码
  0  成功（假设为 0 条也算成功：报告里写明没有达到门槛的重复失败）
  1  输入目录缺 cases.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "benchmark"))

from failure_mining import mine_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D 模块失败归因（D-F4 骨架）")
    parser.add_argument("--run", required=True, help="一次运行的输出目录，需含 cases.jsonl")
    parser.add_argument("--out", default=None, help="结果路径，默认写到 <run>/hypotheses.json")
    args = parser.parse_args(argv)

    run_dir = Path(args.run)
    cases_path = run_dir / "cases.jsonl"
    if not cases_path.is_file():
        print(f"找不到 {cases_path}", file=sys.stderr)
        return 1

    result = mine_file(cases_path)
    out_path = Path(args.out) if args.out else run_dir / "hypotheses.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = result["summary"]
    print(
        f"用例 {summary['caseCount']}，失败记录 {summary['failureRecords']}，"
        f"假设 {summary['hypothesisCount']}，单例被拒 {summary['rejectedCount']}，环境未接线 {summary['excludedCount']}"
    )
    for hypothesis in result["hypotheses"]:
        print(f"  {hypothesis['hypothesisId']} [{hypothesis['category']}] {hypothesis['pattern'][:60]}")
        print(f"    用例 {hypothesis['caseIds']} → 可改 {hypothesis['allowedTargets']}")
    for rejected in result["rejected"]:
        print(f"  被拒 {rejected['kind']}：{rejected['reason']}")
    print(f"结果写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
