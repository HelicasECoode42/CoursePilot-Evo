"""held-out 隔离跑入口：父进程只输出聚合分数，判据不离开子进程。

用法（在仓库根目录）
  python benchmark/run_heldout.py --cases ../restricted/held-out --gold ../restricted/gold \
      --manifest benchmark/manifests/example.json --transport dry
  python benchmark/run_heldout.py ... --transport http --base-url http://127.0.0.1:8000

  --transport dry 只验隔离机制，不发网络请求，结果一律记为占位（DEGRADED），不能当分数。

退出码
  0  子进程正常返回聚合结果
  1  隔离条件不成立（目录在区内、经过软链、子进程失败、输出含判据原句）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "benchmark"))

from heldout import IsolationError, run_heldout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="held-out 隔离跑（D-F2 的留出集侧）")
    parser.add_argument("--cases", required=True, help="held-out 题面目录，必须在工作区之外")
    parser.add_argument("--gold", required=True, help="判据目录，必须在工作区之外")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--transport", default="http", choices=("http", "dry"))
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)

    try:
        payload = run_heldout(
            cases_root=args.cases,
            gold_root=args.gold,
            manifest_path=args.manifest,
            workspace_root=REPO_ROOT,
            transport=args.transport,
            base_url=args.base_url,
            timeout=args.timeout,
        )
    except IsolationError as exc:
        print(f"隔离条件不成立：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.transport == "dry":
        print("注意：dry 模式只验证隔离机制，聚合分数不具意义", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
