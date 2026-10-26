"""组合启动脚本的自测：钉住 Java 探针口径、服务密钥映射、mysql 的 N/A 语义与相对路径启动命令解析。

不起真进程（除 resolve 用的临时可执行文件外），不连服务。
"""

from __future__ import annotations

import stat
from pathlib import Path

import start_stack
from stack_config import NOT_APPLICABLE, SPECS

SVC = {s["name"]: s for s in start_stack.SERVICES}


def values_with(**over) -> dict:
    values = {s.key: (s.default if s.default is not None else "filled") for s in SPECS}
    values.update(over)
    return values


def test_java_probe_is_tcp_only_because_actuator_is_not_in_pom():
    # pom.xml 未引入 actuator：不能再探 /actuator/health
    java = SVC["java"]
    assert java["health_path"] is None
    assert "actuator" in java["cmd_source"]
    assert java["url_key"] == "CP_JAVA_BASE_URL"


def test_java_ready_is_tcp_level_when_port_open(monkeypatch):
    monkeypatch.setattr(start_stack, "tcp_open", lambda host, port, timeout=2.0: True)
    verdict = start_stack.judge(SVC["java"], values_with(), probe=True)
    assert verdict["status"] == "READY"
    assert "TCP 127.0.0.1:8081" in verdict["detail"]


def test_java_default_port_matches_actual_server_port():
    # application.properties 的 server.port=8081
    assert start_stack.target(SVC["java"], values_with()) == ("127.0.0.1", 8081)


def test_java_gets_service_key_mapped_to_its_own_variable_name(monkeypatch):
    monkeypatch.delenv("COURSEPILOT_SERVICE_KEY", raising=False)
    env = start_stack.child_env(SVC["java"], values_with(CP_SERVICE_KEY="svc-from-config"))
    assert env["COURSEPILOT_SERVICE_KEY"] == "svc-from-config"


def test_services_without_env_map_do_not_receive_the_java_key(monkeypatch):
    monkeypatch.delenv("COURSEPILOT_SERVICE_KEY", raising=False)
    env = start_stack.child_env(SVC["api"], values_with(CP_SERVICE_KEY="svc-from-config"))
    assert "COURSEPILOT_SERVICE_KEY" not in env


def test_mysql_is_not_applicable_and_keeps_its_reason_visible():
    verdict = start_stack.judge(SVC["mysql"], values_with(), probe=True)
    assert verdict["status"] == "N/A"
    assert NOT_APPLICABLE["mysql"] in verdict["detail"]
    assert "H2" in verdict["detail"]


def test_mysql_na_never_counts_as_ready_and_never_fails_the_run_alone():
    na = {"name": "mysql", "status": "N/A"}
    assert start_stack.exit_status([na, {"name": "java", "status": "PLAN"}]) == 0
    assert start_stack.exit_status([na, {"name": "java", "status": "READY"}]) == 0


def test_other_services_blocked_still_fail_the_run_with_mysql_na():
    na = {"name": "mysql", "status": "N/A"}
    for bad in ("BLOCKED", "MISSING", "UNREACHABLE", "TIMEOUT"):
        assert start_stack.exit_status([na, {"name": "java", "status": bad}]) == 1, bad


def test_a_service_without_inapplicable_mark_and_without_command_is_still_blocked():
    svc = {"name": "x", "owner": "?", "module": "x", "manifest": None, "start_cmd": None, "cmd_source": "未登记"}
    assert start_stack.judge(svc, values_with(), probe=False)["status"] == "BLOCKED"


def test_plan_mode_exit_code_matches_real_run_rule():
    # 计划模式下 mysql=N/A，其余为 PLAN：退出码 0，与真跑同一条规则
    plan = [start_stack.judge(s, values_with(), probe=False) for s in start_stack.SERVICES]
    assert start_stack.exit_status(plan) == 0


def test_relative_start_command_resolves_inside_module_dir(tmp_path):
    module = tmp_path / "svc"
    module.mkdir()
    tool = module / "run-me"
    tool.write_text("#!/bin/sh\n", encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    resolved = start_stack.resolve_command(["./run-me", "-B"], module)
    assert resolved == [str(tool.resolve()), "-B"]


def test_missing_relative_command_is_unresolvable_not_a_crash(tmp_path):
    assert start_stack.resolve_command(["./no-such-tool"], tmp_path) is None


def test_relative_command_is_not_looked_up_in_the_caller_directory(tmp_path, monkeypatch):
    # 旧写法 shutil.which("./mvnw") 只看进程当前目录；模块里有、仓库根没有时必须仍能解析
    module = tmp_path / "java"
    module.mkdir()
    wrapper = module / "mvnw"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    monkeypatch.chdir(tmp_path.parent)
    assert start_stack.resolve_command(["./mvnw", "-B"], module) is not None


def test_java_start_command_is_module_relative_wrapper():
    head = SVC["java"]["start_cmd"][0]
    assert head in ("./mvnw", "./mvnw.cmd")
    assert Path(head).name.startswith("mvnw")
