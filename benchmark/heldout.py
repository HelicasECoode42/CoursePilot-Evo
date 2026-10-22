"""held-out 隔离跑：父进程只拿到聚合分数，判据与题面只在子进程里出现。

为什么这样做
  docs/07 第 4 节要求「独立 Runner 才能读取 held-out 题面与标签并评分」，候选与归因侧不得读取标准答案。
  本机没有真正的进程隔离沙箱，所以用两条可验证的约束来近似：
    1 路径约束：held-out 与判据目录必须在仓库工作区之外，且路径上不得有软链（软链会把内容带回工作区）；
    2 数据约束：判据只在子进程里读，子进程只输出聚合结果，并在输出前自检输出里不含判据原句。

边界
  这不是权限隔离，是同机进程与约定层面的隔离；真隔离（容器/独立账号）留给部署侧。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE_MARKER = ".git"


class IsolationError(RuntimeError):
    """隔离条件不成立：路径在区内、经过软链、子进程失败或输出泄漏判据。"""


def assert_outside_workspace(path: str | Path, workspace_root: str | Path, *, label: str) -> Path:
    """确认目录在工作区之外，且路径上每一段都不是软链。

    软链要在 resolve 之前逐段检查：解析之后链接已被跟随，看不出它指向哪里。
    """
    raw = Path(path)
    if not raw.exists():
        raise IsolationError(f"{label} 不存在：{raw}")
    absolute = raw if raw.is_absolute() else (Path.cwd() / raw)
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise IsolationError(f"{label} 的路径经过软链：{cursor}")
    resolved = absolute.resolve()
    workspace = Path(workspace_root).resolve()
    if resolved == workspace or workspace in resolved.parents:
        raise IsolationError(f"{label} 位于工作区内：{resolved}")
    return resolved


def run_heldout(
    *,
    cases_root: str | Path,
    gold_root: str | Path,
    manifest_path: str | Path,
    workspace_root: str | Path,
    transport: str = "http",
    base_url: str | None = None,
    timeout: float = 300.0,
    python: str | None = None,
) -> dict[str, Any]:
    """在子进程里跑 held-out，返回子进程给出的聚合结果。"""
    cases = assert_outside_workspace(cases_root, workspace_root, label="held-out 题面目录")
    gold = assert_outside_workspace(gold_root, workspace_root, label="判据目录")
    manifest = Path(manifest_path)
    if not manifest.is_file():
        raise IsolationError(f"manifest 不存在：{manifest}")

    repo_root = Path(workspace_root)
    env = dict(os.environ)
    env.update(
        {
            "CP_HELDOUT_CASES": str(cases),
            "CP_HELDOUT_GOLD": str(gold),
            "CP_HELDOUT_MANIFEST": str(manifest),
            "CP_HELDOUT_TRANSPORT": transport,
            "PYTHONIOENCODING": "utf-8",
        }
    )
    if base_url:
        env["CP_HELDOUT_BASE_URL"] = base_url

    completed = subprocess.run(
        [python or sys.executable, str(repo_root / "benchmark" / "heldout_worker.py")],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()[-3:]
        raise IsolationError(f"隔离子进程失败（退出码 {completed.returncode}）：" + " | ".join(tail))

    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    if not lines:
        raise IsolationError("隔离子进程没有输出")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise IsolationError(f"隔离子进程输出不是 JSON：{exc}") from None

    if not payload.get("leakFree", False):
        raise IsolationError("隔离子进程自检发现输出里含判据原句")
    if "cases" in payload or "verdicts" in json.dumps(payload):
        raise IsolationError("隔离子进程返回了逐例判据：只允许聚合结果")
    return payload
