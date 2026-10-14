"""D2 组合启动脚本：一条命令拉起 MySQL / Java / Python / Web，并判定是否就绪。

规则（取自 Issue #12 的验收条件）
  必需服务缺失、启动命令未登记、或超时就绪 → 退出码非 0；不允许 SKIP 算通过。
  模型可以用受控假响应，但 Java / HTTP / DB / UI 必须真实。

服务登记表
  只登记「有书面依据」的启动命令；没有依据的一律留空并判 BLOCKED（未登记），不猜命令。
  mysql 的本地启动方式环境相关，本脚本只做可达性判定；CI 侧由 workflow 的 services 提供。

用法
  python integration/start_stack.py --plan     # 只判定与打印计划，不启动任何进程，退出码与真跑一致
  python integration/start_stack.py            # 真启动并等待就绪
  python integration/start_stack.py --only java --only api
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stack_config import ROOT, errors, resolve, validate

LOG_DIR = ROOT / "runs" / "stack"

SERVICES: tuple[dict, ...] = (
    {
        "name": "mysql",
        "owner": "B（B1 环境）",
        "module": "(环境，本仓库内无模块)",
        "manifest": None,
        "start_cmd": None,
        "cmd_source": "待 B 落地后登记本地启动方式；CI 侧用 workflow 的 services: mysql",
        "health_path": None,
        "host_key": "CP_MYSQL_HOST",
        "port_key": "CP_MYSQL_PORT",
    },
    {
        "name": "java",
        "owner": "B",
        "module": "java-environment",
        "manifest": "pom.xml",
        "start_cmd": ["./mvnw", "-B", "spring-boot:run"],
        "cmd_source": "Spring Boot 约定命令；待 B 的 README 确认后转正",
        "health_path": "/actuator/health",
        "url_key": "CP_JAVA_BASE_URL",
    },
    {
        "name": "api",
        "owner": "C",
        "module": "agent-runtime",
        "manifest": "pyproject.toml",
        "start_cmd": None,
        "cmd_source": "待 C 的 README 登记启动命令（W1 骨架尚未写）",
        "health_path": "/health",
        "url_key": "CP_API_BASE_URL",
    },
    {
        "name": "web",
        "owner": "E",
        "module": "web",
        "manifest": "package.json",
        "start_cmd": ["npm", "run", "dev"],
        "cmd_source": "Vite 约定命令；待 E 的 package.json 确认后转正",
        "health_path": "/",
        "url_key": "CP_WEB_BASE_URL",
    },
)


def target(svc: dict, values: dict):
    """返回 (host, port)。"""
    if "url_key" in svc:
        parsed = urlparse(values[svc["url_key"]])
        return parsed.hostname or "127.0.0.1", parsed.port or (443 if parsed.scheme == "https" else 80)
    return values[svc["host_key"]], int(values[svc["port_key"]])


def tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def http_ok(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except URLError as e:
        return False, f"未就绪（{type(e).__name__}）"
    except Exception as e:  # noqa: BLE001
        return False, f"未就绪（{type(e).__name__}）"


def judge(svc: dict, values: dict, probe: bool = True) -> dict:
    """不启动任何进程，只给判定：MISSING / BLOCKED / READY / UNREACHABLE。"""
    result = {"name": svc["name"], "owner": svc["owner"], "status": "", "detail": "", "next": ""}
    if svc["manifest"]:
        manifest = ROOT / svc["module"] / svc["manifest"]
        if not manifest.is_file():
            result["status"] = "MISSING"
            result["detail"] = f"模块 {svc['module']} 尚未实现（缺 {svc['module']}/{svc['manifest']}）"
            result["next"] = f"由 {svc['owner']} 交付该模块"
            return result
    if svc["start_cmd"] is None:
        result["status"] = "BLOCKED"
        result["detail"] = "启动命令未登记"
        result["next"] = svc["cmd_source"]
        return result
    host, port = target(svc, values)
    if not probe:
        result["status"] = "PLAN"
        result["detail"] = f"将启动并等待 {host}:{port}"
        return result
    if tcp_open(host, port):
        if svc["health_path"] is None:
            result["status"] = "READY"
            result["detail"] = f"TCP {host}:{port} 可达"
            return result
        parsed = urlparse(values[svc["url_key"]])
        ok, how = http_ok(f"{parsed.scheme}://{host}:{port}{svc['health_path']}")
        result["status"] = "READY" if ok else "UNREACHABLE"
        result["detail"] = f"TCP 可达；{svc['health_path']} {how}"
        if not ok:
            result["next"] = f"确认 {svc['module']} 已启动且健康路径为 {svc['health_path']}"
        return result
    result["status"] = "UNREACHABLE"
    result["detail"] = f"TCP {host}:{port} 不可达"
    result["next"] = svc["cmd_source"] if svc["start_cmd"] is None else f"启动 {svc['module']}（{svc['cmd_source']}）"
    return result


def start_service(svc: dict, values: dict) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / f"{svc['name']}.log", "w", encoding="utf-8")  # noqa: SIM115
    return subprocess.Popen(svc["start_cmd"], cwd=ROOT / svc["module"], stdout=log, stderr=subprocess.STDOUT)


def wait_ready(svc: dict, values: dict, timeout: float, interval: float) -> dict:
    deadline = time.monotonic() + timeout
    last = judge(svc, values)
    while time.monotonic() < deadline:
        if last["status"] == "READY":
            return last
        time.sleep(interval)
        last = judge(svc, values)
    last["status"] = "TIMEOUT" if last["status"] != "READY" else "READY"
    last["next"] = last.get("next") or f"查看 runs/stack/{svc['name']}.log"
    return last


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 组合启动脚本")
    ap.add_argument("--plan", action="store_true", help="只判定与打印计划，不启动进程")
    ap.add_argument("--only", action="append", default=[], help="只处理指定服务，可重复")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args(argv)

    values, _sources, used_file = resolve(Path(args.env_file) if args.env_file else None)
    problems = validate(values)
    if errors(problems):
        print("配置校验未通过，先修配置再启动服务：")
        for level, key, message in problems:
            if level == "error":
                print(f"  ERROR {key}: {message}")
        print(f"\n配置来源：{used_file}；模板：integration/stack.env.example")
        return 1

    picked = [s for s in SERVICES if not args.only or s["name"] in args.only]
    timeout = float(values["CP_HEALTH_TIMEOUT_SECONDS"])
    interval = float(values["CP_HEALTH_POLL_SECONDS"])
    procs: dict[str, subprocess.Popen] = {}
    results: list[dict] = []

    try:
        for svc in picked:
            verdict = judge(svc, values, probe=not args.plan)
            if args.plan:
                results.append(verdict)
                continue
            if verdict["status"] in ("MISSING", "BLOCKED"):
                results.append(verdict)
                continue
            if verdict["status"] == "READY":
                results.append(verdict)
                continue
            procs[svc["name"]] = start_service(svc, values)
            results.append(wait_ready(svc, values, timeout, interval))
    finally:
        for proc in procs.values():
            proc.terminate()
        if procs:
            print(f"已停止本次启动的 {len(procs)} 个进程；日志见 runs/stack/")

    if args.json:
        print(
            json.dumps(
                {"plan": args.plan, "configFile": str(used_file), "services": results}, ensure_ascii=False, indent=2
            )
        )
    else:
        print(f"配置：{used_file}")
        print(f"{'服务':<8} {'状态':<12} {'负责':<10} 说明")
        for r in results:
            print(f"{r['name']:<8} {r['status']:<12} {r['owner']:<10} {r['detail']}")
        todo = [r for r in results if r["status"] not in ("READY", "PLAN")]
        if todo:
            print("\n未就绪的服务与下一步：")
            for r in todo:
                print(f"  {r['name']}（{r['owner']}）：{r['next']}")
        ready = sum(1 for r in results if r["status"] == "READY")
        print(
            f"\n就绪 {ready}/{len(results)}；"
            + ("全部就绪。" if ready == len(results) else "存在未就绪服务，退出码 1（不允许跳过算通过）")
        )

    return 0 if all(r["status"] in ("READY", "PLAN") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
