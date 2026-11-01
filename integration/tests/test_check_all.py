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
    base = {
        "plan": False,
        "keep": False,
        "driver": "auto",
        "stub_url": None,
        "web_with_stub": False,
        "controlled_model": False,
    }
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


def test_browser_stub_mode_is_explicitly_forwarded():
    web = build_argv("check_web.py", (), ns(driver="playwright", web_with_stub=True))
    assert web[-3:] == ["--driver", "playwright", "--with-stub"]


def test_controlled_model_mode_is_only_forwarded_to_model_checks():
    args = ns(controlled_model=True)
    assert build_argv("check_stack.py", (), args)[-1] == "--controlled-model"
    assert build_argv("smoke_stack.py", (), args)[-1] == "--controlled-model"
    assert "--controlled-model" not in build_argv("check_web.py", (), args)


def test_smoke_stops_after_record_failure_instead_of_using_example_id(monkeypatch):
    import smoke_stack
    from stack_checks import FAIL, PASS, StepResult

    monkeypatch.setattr(smoke_stack, "resolve", lambda _: ({"CP_API_BASE_URL": "http://127.0.0.1:8000"}, {}, None))
    monkeypatch.setattr(smoke_stack, "errors", lambda _: [])
    monkeypatch.setattr(smoke_stack, "validate", lambda _: [])
    monkeypatch.setattr(smoke_stack, "readiness", lambda _: {"api": "READY", "java": "READY"})
    monkeypatch.setattr(
        smoke_stack,
        "step_sessions",
        lambda chain: StepResult("sessions", PASS, "s1", "201", "HTTP 201"),
    )
    monkeypatch.setattr(
        smoke_stack,
        "step_record",
        lambda chain: StepResult("record", FAIL, "r1", "201", "HTTP 503"),
    )
    results, _, _ = smoke_stack.run_smoke(plan_only=False, transport=object())
    assert [result.step for result in results] == ["record"]
    assert results[0].verdict == FAIL


def test_entry_does_not_run_dependent_checks_after_stack_start_failure(monkeypatch, capsys):
    import check_all

    called = []

    def fake_run(argv, capture):
        script = Path(argv[1]).name
        called.append(script)
        return (2 if script == "start_stack.py" else 0), ""

    monkeypatch.setattr(check_all, "run_step", fake_run)
    assert check_all.main(["--json", "--keep"]) == 1
    output = capsys.readouterr().out
    payload = json.loads(output[output.index("{\n"):])
    assert called == ["stack_config.py", "start_stack.py"]
    assert payload["failed"] == ["组合启动", "主链路检查", "异常与未知覆盖", "受控假响应", "浏览器检查"]


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
