"""D2 统一配置入口：全组一份配置，缺必要项就失败，不默认放行。

口径来源
  docs/16：全组用唯一配置入口；端口/timeouts/CORS 都是环境配置；服务启动校验缺必要配置并失败，
           不能默认使用硬编码密钥或宽松公网 origin。
  docs/03：默认本地 Web 5173、Python 8000、Java 8080、MySQL 3306，均配置化。
           注意：docs/03 写的 Java 8080 与实际服务不一致，本文件的 Java 默认值以实际服务为准（8081，
           见 java-environment/src/main/resources/application.properties 的 server.port=8081）。
           docs/03 不归本模块，需要由其所有者对齐。
  docs/04：Java 要 X-Service-Key，由 Python 配置提供；密钥仅在环境变量，不进仓库/Prompt/Trace；
           CORS 仅允许配置的 Web origin，不能是通配。
  C 模块（agent-runtime/.env.example）：键名用 CP_ 前缀；模型端点留空时走受控 stub。

配置文件位置
  模板：integration/stack.env.example（入库，只有占位值）
  真实：data/private/stack.env（已被 .gitignore 覆盖，实测确认；密钥只能放这里或环境变量）
  可用环境变量 CP_STACK_ENV 指定其它位置；环境变量优先于文件。

判定等级
  error   缺必要项、密钥占位、URL/端口非法、服务端口冲突 → 退出码 1
  warning 非 loopback 监听、模型端点留空（受控 stub）、
          当前不适用服务（NOT_APPLICABLE）的必填项未填   → 退出码 0（仍逐条可见）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = ROOT / "data" / "private" / "stack.env"
EXAMPLE_ENV_FILE = Path(__file__).resolve().parent / "stack.env.example"

# 只是示例里出现过的占位串，出现即视为未配置
PLACEHOLDERS = {
    "changeme",
    "change_me",
    "placeholder",
    "your-key-here",
    "***",
    "todo",
    "xxx",
    "cp_mod...lder",
}


@dataclass(frozen=True)
class Spec:
    key: str
    service: str
    default: str | None  # None = 必填，没有默认值
    secret: bool
    note: str


SPECS: tuple[Spec, ...] = (
    Spec("CP_MYSQL_HOST", "mysql", "127.0.0.1", False, "数据库主机（本地默认 loopback）"),
    Spec("CP_MYSQL_PORT", "mysql", "3306", False, "数据库端口（docs/03 默认 3306）"),
    Spec("CP_MYSQL_DB", "mysql", None, False, "库名，必填"),
    Spec("CP_MYSQL_USER", "mysql", None, False, "账号，必填"),
    Spec("CP_MYSQL_PASSWORD", "mysql", None, True, "口令，必填；只放环境变量或 data/private/stack.env"),
    Spec(
        "CP_JAVA_BASE_URL",
        "java",
        "http://127.0.0.1:8081",
        False,
        "B 的事实 API（实际 server.port=8081，与 docs/03 的 8080 不一致，以实际为准）",
    ),
    Spec(
        "CP_SERVICE_KEY",
        "java",
        None,
        True,
        "Python→Java 的 X-Service-Key（docs/04），必填；start_stack 启动 Java 时映射为子进程环境变量 "
        "COURSEPILOT_SERVICE_KEY（Java 侧变量名不改）",
    ),
    Spec("CP_API_BASE_URL", "api", "http://127.0.0.1:8000", False, "C 的网关（docs/03 默认 8000）"),
    Spec("CP_WEB_BASE_URL", "web", "http://127.0.0.1:5173", False, "E 的页面（docs/03 默认 5173）"),
    Spec("CP_CORS_ORIGINS", "api", "http://127.0.0.1:5173", False, "只允许配置的 Web origin；禁通配"),
    Spec("CP_MODEL_BASE_URL", "api", "", False, "模型端点；留空 = 用受控 stub（C 的 W1 行为）"),
    Spec("CP_MODEL_API_KEY", "api", "", True, "模型密钥；留空表示不需要"),
    Spec("CP_HEALTH_TIMEOUT_SECONDS", "common", "60", False, "就绪等待上限（秒）"),
    Spec("CP_HEALTH_POLL_SECONDS", "common", "2", False, "就绪轮询间隔（秒）"),
    Spec("CP_START_COMMAND_TIMEOUT_SECONDS", "common", "180", False, "启动命令的等待上限（秒）"),
)
BY_KEY = {s.key: s for s in SPECS}

# 当前技术栈不适用的服务：必填项不挡配置校验（改为 warning 逐条可见），启动脚本判 N/A。
# 唯一来源：start_stack.py 的 mysql 登记项从这里取原因，两处不另写一份。
# B 引入 MySQL 后删掉这一条即恢复为必填、必需服务。
NOT_APPLICABLE: dict[str, str] = {
    "mysql": "B 当前用 H2 文件库（application.properties 的 jdbc:h2:file），pom.xml 无 MySQL 驱动、无 Flyway；B 引入 MySQL 后再登记",
}
URL_KEYS = ("CP_JAVA_BASE_URL", "CP_API_BASE_URL", "CP_WEB_BASE_URL")


def read_env_file(path: Path) -> dict[str, str]:
    """读 KEY=VALUE；忽略空行与 # 注释；去掉成对引号。文件不存在返回空字典。"""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def resolve(env_file: Path | None = None, environ: dict[str, str] | None = None):
    """返回 (值, 来源)。来源取值 file / env / default。"""
    environ = os.environ if environ is None else environ
    env_file = Path(environ.get("CP_STACK_ENV", env_file or DEFAULT_ENV_FILE))
    file_values = read_env_file(env_file)
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for spec in SPECS:
        if spec.key in environ and environ[spec.key] != "":
            values[spec.key], sources[spec.key] = environ[spec.key], "env"
        elif spec.key in file_values:
            values[spec.key], sources[spec.key] = file_values[spec.key], "file"
        elif spec.default is not None:
            values[spec.key], sources[spec.key] = spec.default, "default"
        else:
            values[spec.key], sources[spec.key] = "", "missing"
    return values, sources, env_file


def _is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def validate(values: dict[str, str]) -> list[tuple[str, str, str]]:
    """返回 [(等级, 键, 说明)]。等级为 error 时调用方应非零退出。"""
    problems: list[tuple[str, str, str]] = []

    for spec in SPECS:
        value = (values.get(spec.key) or "").strip()
        if spec.default is None and not value:
            if spec.service in NOT_APPLICABLE:
                problems.append(
                    ("warning", spec.key, f"{spec.service} 当前不适用，必填项暂不校验（原因见 start_stack 的服务表）")
                )
            else:
                problems.append(("error", spec.key, f"必填项缺失（{spec.service} 需要）；{spec.note}"))
        elif spec.secret and value.lower() in PLACEHOLDERS:
            problems.append(("error", spec.key, "仍是占位值，不是可用密钥"))

    for key in URL_KEYS:
        value = (values.get(key) or "").strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            problems.append(("error", key, f"不是合法的 http(s) 地址：{value}"))
        elif not _is_loopback(parsed.hostname):
            problems.append(
                ("warning", key, f"指向非 loopback 主机 {parsed.hostname}；本地骨架不应开放公网（docs/04）")
            )

    for key in (
        "CP_MYSQL_PORT",
        "CP_HEALTH_TIMEOUT_SECONDS",
        "CP_HEALTH_POLL_SECONDS",
        "CP_START_COMMAND_TIMEOUT_SECONDS",
    ):
        value = (values.get(key) or "").strip()
        try:
            number = int(value)
        except ValueError:
            problems.append(("error", key, f"必须是整数，现在是 {value!r}"))
            continue
        if key == "CP_MYSQL_PORT" and not 1 <= number <= 65535:
            problems.append(("error", key, f"端口越界：{number}"))
        if key != "CP_MYSQL_PORT" and number <= 0:
            problems.append(("error", key, f"必须为正数：{number}"))

    origins = [o.strip() for o in (values.get("CP_CORS_ORIGINS") or "").split(",") if o.strip()]
    if not origins:
        problems.append(("error", "CP_CORS_ORIGINS", "至少要有一个 origin"))
    for origin in origins:
        if "*" in origin:
            problems.append(("error", "CP_CORS_ORIGINS", f"不允许通配 origin：{origin}"))
            continue
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            problems.append(("error", "CP_CORS_ORIGINS", f"origin 非法：{origin}"))

    ports: dict[int, str] = {}
    for key in URL_KEYS:
        parsed = urlparse((values.get(key) or "").strip())
        if not parsed.hostname:
            continue
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port in ports and ports[port] != key:
            problems.append(("error", key, f"端口 {port} 与 {ports[port]} 冲突"))
        ports.setdefault(port, key)
    mysql_port = (values.get("CP_MYSQL_PORT") or "").strip()
    if mysql_port.isdigit() and int(mysql_port) in ports:
        problems.append(("error", "CP_MYSQL_PORT", f"端口 {mysql_port} 与 {ports[int(mysql_port)]} 冲突"))

    if not (values.get("CP_MODEL_BASE_URL") or "").strip():
        problems.append(("warning", "CP_MODEL_BASE_URL", "留空 → 走受控 stub 模型；真实模型全链路属每周验收另跑"))
    return problems


def errors(problems) -> list[tuple[str, str, str]]:
    return [p for p in problems if p[0] == "error"]


def masked(values: dict[str, str]) -> dict[str, str]:
    """密钥一律不打印内容，只显示是否已配置。"""
    return {k: ("***已配置***" if v else "***空***") if BY_KEY[k].secret else v for k, v in values.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 统一配置入口：校验全组配置")
    ap.add_argument("--check", action="store_true", help="校验并打印（默认）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--export", action="store_true", help="输出 shell export 行（密钥原样，仅给本机 shell 用）")
    ap.add_argument("--env-file", default=None, help="配置文件路径，默认 data/private/stack.env")
    args = ap.parse_args(argv)

    values, sources, used_file = resolve(Path(args.env_file) if args.env_file else None)
    problems = validate(values)

    if args.export:
        for spec in SPECS:
            print(f"export {spec.key}={json.dumps(values[spec.key], ensure_ascii=False)}")
        return 1 if errors(problems) else 0

    if args.json:
        print(
            json.dumps(
                {
                    "envFile": str(used_file),
                    "envFileExists": used_file.is_file(),
                    "values": masked(values),
                    "sources": sources,
                    "problems": [{"level": lv, "key": k, "message": m} for lv, k, m in problems],
                    "ok": not errors(problems),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if errors(problems) else 0

    print(f"配置文件：{used_file}（{'存在' if used_file.is_file() else '不存在，全部取默认值'}）")
    print(f"模板参考：{EXAMPLE_ENV_FILE.relative_to(ROOT)}")
    print()
    print(f"{'键':<32} {'服务':<8} {'来源':<8} 值")
    for spec in SPECS:
        shown = masked({spec.key: values[spec.key]})[spec.key]
        print(f"{spec.key:<32} {spec.service:<8} {sources[spec.key]:<8} {shown}")
    print()
    if not problems:
        print("配置校验通过：无 error、无 warning。")
        return 0
    for level, key, message in problems:
        print(f"{level.upper():<8} {key}: {message}")
    bad = len(errors(problems))
    print()
    print(f"共 {len(problems)} 条（error {bad}，warning {len(problems) - bad}）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
