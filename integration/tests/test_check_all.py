"""第 7 件（一条入口）的自测：入口参数拼装 + --keep/--stop 的 PID 收尾。

PID 那条用真进程验证（起一个睡眠进程、写 PID 文件、调 stop_recorded，确认它真的被停掉），
其余是纯参数拼装断言，不连服务。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import start_stack
from check_all import build_argv

HERE = Path(__file__).resolve().parents[1]


def ns(**over) -> argparse.Namespace:
    base = {"plan": False, "keep": False, "driver": "auto", "stub_url": None}
    base.update(over)
    return argparse.Namespace(**base)


def test_plan_mode_passes_plan_to_the_checks_that_need_it():
    argv = build_argv("start_stack.py", (), ns(plan=True))
    assert argv[-1] == "--plan"
    assert build_argv("check_stack.py", (), ns(plan=True))[-1] == "--plan"
    assert build_argv("smoke_stack.py", (), ns(plan=True))[-1] == "--plan"
    assert "--plan" not in build_argv("stack_config.py", ("--check",), ns(plan=True))


def test_real_run_keeps_services_and_passes_driver():
    assert build_argv("start_stack.py", (), ns())[-1] == "--keep"
    web = build_argv("check_web.py", (), ns(driver="playwright"))
    assert web[-2:] == ["--driver", "playwright"]
    with_stub = build_argv("check_web.py", (), ns(stub_url="http://127.0.0.1:8099"))
    assert with_stub[-2:] == ["--stub-url", "http://127.0.0.1:8099"]


def test_entry_scripts_exist_and_are_runnable():
    for script in ("stack_config.py", "start_stack.py", "check_stack.py", "smoke_stack.py", "check_web.py"):
        assert (HERE / script).is_file(), script


def test_stop_recorded_terminates_the_process_it_recorded(tmp_path, monkeypatch):
    pid_file = tmp_path / "pids.json"
    monkeypatch.setattr(start_stack, "PID_FILE", pid_file)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        pid_file.write_text(json.dumps({"dummy": {"pid": proc.pid, "argv": ["sleep"]}}), encoding="utf-8")
        assert start_stack.stop_recorded() == 0
        for _ in range(50):
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        assert proc.poll() is not None, "stop_recorded 没有停掉记录的进程"
        assert not pid_file.exists(), "PID 文件应在本轮收尾后删除"
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stop_recorded_is_a_noop_without_a_pid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(start_stack, "PID_FILE", tmp_path / "missing.json")
    assert start_stack.stop_recorded() == 0


def test_stop_step_never_carries_keep():
    from check_all import STOP_STEP

    argv = [sys.executable, "start_stack.py", *STOP_STEP[3]]
    assert argv[-1] == "--stop"
    assert "--keep" not in argv
