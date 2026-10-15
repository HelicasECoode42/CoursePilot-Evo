"""D2 浏览器检查（第 5 件事的框架）：主路径、未知与服务失败三档。

检查项与观察点见 `web_checks.py` 顶部，全部取自 E 的页面实现与 README。本脚本只负责
判定顺序、驱动选择、输出与退出码：缺服务判 BLOCKED、缺浏览器判 BLOCKED、缺受控假响应判 BLOCKED，
都不跳过、都不算过。

用法
  python integration/check_web.py --plan                      # 只判定与打印计划，不连页面
  python integration/check_web.py                             # 真跑（默认从配置取 CP_WEB_BASE_URL）
  python integration/check_web.py --driver playwright         # 指定真浏览器驱动
  python integration/check_web.py --stub-url http://127.0.0.1:8099   # 受控假响应下的「答未知」分支
  python integration/check_web.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stack_checks import (
    BLOCKED,
    PASS,
    PLAN,
    StepResult,
    exit_code,
    format_failures,
    summarize,
)
from stack_config import errors, resolve, validate
from start_stack import SERVICES, judge
from web_checks import (
    CHECK_EXPECT,
    CHECK_ORDER,
    EVIDENCE_DIR,
    PlaywrightDriver,
    pick_driver,
    plan_rows,
    run_web_checks,
)

START_HINT = "cd web && npm ci && npm run dev（127.0.0.1:5173）"


def service_states(plan_only: bool) -> tuple[dict[str, str], dict[str, str]]:
    values, _sources, _file = resolve(None)
    return values, {svc["name"]: judge(svc, values, probe=not plan_only)["status"] for svc in SERVICES}


def blocked_rows(detail: str, repro: str) -> list[StepResult]:
    return [
        StepResult(name, BLOCKED, "-", CHECK_EXPECT[name], detail, detail=detail, repro=repro) for name in CHECK_ORDER
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 浏览器检查")
    ap.add_argument("--plan", action="store_true", help="只判定与打印计划，不连页面")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--driver", choices=("auto", "http", "playwright"), default="auto", help="驱动选择")
    ap.add_argument("--web-url", default=None, help="页面地址，默认取配置 CP_WEB_BASE_URL")
    ap.add_argument("--api-url", default=None, help="Python 地址，默认取配置 CP_API_BASE_URL")
    ap.add_argument("--stub-url", default=None, help="受控假响应页面地址，用于「答未知」分支")
    args = ap.parse_args(argv)

    values, states = service_states(args.plan)
    problems = errors(validate(values))
    if problems:
        print(f"配置校验未通过（{len(problems)} 条 error）：{problems[0][1]} {problems[0][2]}")
        return 1

    web_url = args.web_url or values["CP_WEB_BASE_URL"]
    api_reachable = states.get("api") == "READY"
    driver = pick_driver(args.driver)
    available, why = driver.available()

    web_state = states.get("web", "MISSING")
    if args.plan:
        results = (
            plan_rows()
            if web_state in ("READY", "PLAN")
            else blocked_rows(f"服务 web 状态 {web_state}", "python integration/start_stack.py --plan")
        )
        blocked_reason = None if web_state in ("READY", "PLAN") else f"web 未就绪（{web_state}）"
    elif web_state != "READY":
        results = blocked_rows(f"服务 web 状态 {web_state}，浏览器检查无法开始", START_HINT)
        blocked_reason = f"web 未就绪（{web_state}）"
    else:
        results = run_web_checks(driver, web_url, api_reachable, args.stub_url)
        blocked_reason = None

    code = exit_code(results) if results else 1

    if args.json:
        print(
            json.dumps(
                {
                    "mode": "plan" if args.plan else "run",
                    "driver": {"name": driver.name, "available": available, "note": why},
                    "webUrl": web_url,
                    "apiReachable": api_reachable,
                    "stubUrl": args.stub_url,
                    "services": states,
                    "blocked": blocked_reason,
                    "checks": [r.as_dict() for r in results],
                    "summary": summarize(results),
                    "exitCode": code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return code

    print("D2 浏览器检查：" + ("计划模式（不连页面）" if args.plan else "真跑"))
    print(f"驱动：{driver.name}（{'可用' if available else '不可用'}：{why}）")
    if args.driver == "auto" and not PlaywrightDriver().available()[0]:
        print(f"提示：真浏览器未启用（{PlaywrightDriver().available()[1]}）→ 需要 JS 的检查会判 BLOCKED")
    print(
        f"页面：{web_url}｜Python 可达：{api_reachable}｜截图目录：{EVIDENCE_DIR.relative_to(Path(__file__).resolve().parent.parent)}"
    )
    print("服务就绪：" + "、".join(f"{k}={v}" for k, v in states.items()))
    print()
    print(f"{'检查项':<16} {'判定':<10} 期望摘要")
    for result in results:
        print(f"{result.step:<16} {result.verdict:<10} {result.expect}")
    print()
    bad = [r for r in results if r.verdict not in (PASS, PLAN)]
    if bad:
        print("未通过项（五段式，可直接贴到 Issue）：")
        print()
        print(format_failures(results, code))
    if blocked_reason:
        print()
        print(f"阻塞：{blocked_reason}")
    counts = summarize(results)
    print()
    print("汇总：" + "、".join(f"{k} {v}" for k, v in sorted(counts.items())) + f"；退出码 {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
