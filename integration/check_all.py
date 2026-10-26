"""D2 一条入口：配置校验 → 组合启动 → 主链路 → 异常覆盖 → 浏览器检查。

新环境只要两条命令：

    cp integration/stack.env.example data/private/stack.env
    python integration/check_all.py

判定沿用各子检查的五个词，规则只有一条：任一必需服务缺失、任一步不是 PASS，退出码就是 1，
不允许 SKIP 算通过。真跑会以 `--keep` 起服务、跑完自动 `--stop` 收尾；`--plan` 只看计划，不起也不停服务。

用法
  python integration/check_all.py --plan                  # 全部按计划模式，不连服务
  python integration/check_all.py                         # 真跑（HTTP 驱动）
  python integration/check_all.py --driver playwright     # 真跑（需要已装 playwright）
  python integration/check_all.py --keep                  # 跑完保留服务，自己排查用
  python integration/check_all.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# (步骤名, 失败归属, 脚本, 真跑附加参数, 计划模式是否运行)
STEPS: tuple[tuple[str, str, str, tuple[str, ...], bool], ...] = (
    ("配置校验", "D", "stack_config.py", ("--check",), True),
    ("组合启动", "B、C、E", "start_stack.py", (), True),
    ("主链路检查", "B、C", "check_stack.py", (), True),
    ("异常与未知覆盖", "B、C", "smoke_stack.py", (), True),
    ("受控假响应", "D", "check_stub.py", (), False),
    ("浏览器检查", "E", "check_web.py", (), True),
)
STOP_STEP = ("收尾：停止服务", "D", "start_stack.py", ("--stop",))


def build_argv(script: str, extra: tuple[str, ...], args: argparse.Namespace) -> list[str]:
    """拼一步的参数：配置校验没有计划/保留模式；其余步骤在 --plan 下加 --plan，真跑时 start_stack 加 --keep。"""
    argv = [sys.executable, str(HERE / script), *extra]
    if script in ("stack_config.py", "check_stub.py"):
        return argv  # 这两个没有 --plan/--keep 语义
    if args.plan:
        argv.append("--plan")
    elif script == "start_stack.py":
        argv.append("--keep")
    if script == "check_web.py":
        argv += ["--driver", args.driver]
        if args.stub_url:
            argv += ["--stub-url", args.stub_url]
    return argv


def run_step(argv: list[str], capture: bool) -> tuple[int, str]:
    result = subprocess.run(
        argv, cwd=ROOT, capture_output=capture, text=True, encoding="utf-8", errors="replace", check=False
    )
    if capture:
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    return result.returncode, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 一条入口：跑完整条集成检查链")
    ap.add_argument("--plan", action="store_true", help="全部按计划模式：不连服务、不起进程")
    ap.add_argument("--keep", action="store_true", help="真跑时保留已启动的服务（默认跑完 --stop 收尾）")
    ap.add_argument("--driver", choices=("auto", "http", "playwright"), default="auto", help="浏览器检查的驱动")
    ap.add_argument("--stub-url", default=None, help="受控假响应页面地址，透传给浏览器检查")
    ap.add_argument("--json", action="store_true", help="把每一步的退出码与输出打成 JSON")
    args = ap.parse_args(argv)

    print("D2 集成检查链：" + ("计划模式" if args.plan else "真跑"))
    print("框架：" + " → ".join(name for name, *_rest in STEPS))
    print()

    outcomes: list[dict] = []
    for name, owner, script, extra, plan_runs in STEPS:
        step_argv = build_argv(script, extra, args)
        if args.plan and not plan_runs:
            outcomes.append(
                {
                    "name": name,
                    "owner": owner,
                    "argv": step_argv[1:],
                    "exitCode": 0,
                    "note": "计划模式跳过（不依赖外部服务）",
                }
            )
            if not args.json:
                print(f"[{name}] 计划模式跳过：本检查不依赖外部服务，真跑时会执行")
                print()
            continue
        print(f"[{name}] " + " ".join(step_argv[1:]))
        code, output = run_step(step_argv, capture=args.json)
        outcomes.append({"name": name, "owner": owner, "argv": step_argv[1:], "exitCode": code})
        if args.json:
            outcomes[-1]["output"] = output
        else:
            print(f"  → 退出码 {code}" + ("" if code == 0 else f"（未通过，归属 {owner}）"))
        print()

    if not args.plan and not args.keep:
        stop_argv = [sys.executable, str(HERE / STOP_STEP[2]), *STOP_STEP[3]]
        outcomes.append({"name": STOP_STEP[0], "owner": STOP_STEP[1], "argv": stop_argv[1:], "exitCode": 0})
        if not args.json:
            print(f"[{STOP_STEP[0]}] " + " ".join(stop_argv[1:]))
        run_step(stop_argv, capture=args.json)
        print()

    failed = [item for item in outcomes if item["exitCode"] != 0 and item["name"] != STOP_STEP[0]]
    code = 1 if failed else 0

    if args.json:
        print(
            json.dumps(
                {"plan": args.plan, "steps": outcomes, "failed": [f["name"] for f in failed], "exitCode": code},
                ensure_ascii=False,
                indent=2,
            )
        )
        return code

    print(f"{'步骤':<16} {'退出码':<6} 失败归属")
    for item in outcomes:
        note = item.get("note", "")
        print(
            f"{item['name']:<16} {('PLAN' if note else item['exitCode']):<6} {item['owner'] if item['exitCode'] else '-'} {note}"
        )
    print()
    if failed:
        print("未通过：" + "、".join(f"{item['name']}({item['exitCode']}) → {item['owner']}" for item in failed))
        print("五段式失败块在上面对应步骤的输出里；缺服务与行为不符契约都算未通过。")
    elif args.plan:
        # 计划模式只核对了配置和每步的计划，没有连过服务，不能说成全链路通过（AGENTS：不把计划写成真实能力）。
        print("计划检查通过：配置与各步计划一致。这不是全链路通过——计划模式没有连任何服务，真跑请去掉 --plan。")
    else:
        print("全链路通过。")
    print(f"退出码 {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
