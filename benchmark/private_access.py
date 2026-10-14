"""受控入口：工作区外私有资产（gold / held-out / fixtures / 私有评分数据）的唯一读取通道。

为什么需要它
  仓库是公开的，判据与考题存在工作区之外（`restricted/`）。Evolver 不得读取 gold、held-out
  与评分器（AGENTS.md「演化」一节、docs/07）。仅靠目录分离不足以构成证据：需要一条可测试的
  通道，把「谁可以读哪个子目录」写成规则，并拒绝绕过手段。

拒绝的绕过手段
  路径穿越（`..`）、绝对路径、root 之外的符号链接、目录名大小写变体（大小写不敏感的文件系统上
  `GOLD/` 会命中 `gold/`）、空路径、非字符串输入、未声明的角色。

用法
  from private_access import resolve_private, read_private_text
  path = resolve_private(private_root, "gold/G1-001.json", role="runner")

本模块不负责「防止同进程直接 open()」，那是进程与权限边界的事；它负责让「唯一入口」这条规则
可执行、可测试、可留档。
"""

from __future__ import annotations

import os
from pathlib import Path

# 角色 → 允许读取的私有子目录（只写小写原名，大小写必须完全一致）
ROLE_ACCESS = {
    "evolver": frozenset(),
    "runner": frozenset({"gold", "held-out"}),
    "evaluator": frozenset({"gold", "held-out"}),
    "author": frozenset({"gold", "held-out", "fixtures"}),
}


class PrivateAccessError(PermissionError):
    """越权或路径不合法。message 用英文短句，便于断言与日志检索。"""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def resolve_private(private_root, requested, *, role: str) -> Path:
    """把 `requested` 解析成私有根内的绝对路径；不合法或越权时抛 PrivateAccessError。"""
    if not isinstance(private_root, (str, os.PathLike)):
        raise PrivateAccessError("bad_root", f"{type(private_root).__name__}")
    if not isinstance(requested, str) or not requested.strip():
        raise PrivateAccessError("bad_request", repr(requested))
    if "\x00" in requested:
        raise PrivateAccessError("bad_request", "NUL byte")

    allowed = ROLE_ACCESS.get(role)
    if allowed is None:
        raise PrivateAccessError("unknown_role", str(role))

    root = Path(private_root).resolve()
    req = Path(requested.replace("\\", "/"))

    if req.is_absolute():
        raise PrivateAccessError("absolute_path", requested)
    parts = [p for p in req.parts if p not in (".",)]
    if not parts or any(p == ".." for p in parts):
        raise PrivateAccessError("path_traversal", requested)

    if not allowed:
        raise PrivateAccessError("role_denied", f"role={role} may read nothing")

    if parts[0] not in allowed:
        # 大小写变体、未声明的子目录都落到这里
        raise PrivateAccessError("subdir_denied", f"role={role} parts[0]={parts[0]!r}")

    # 逐级检查原始路径上的符号链接：resolve() 之后链接已被跟随，再看不出它原来是链接
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PrivateAccessError("symlink_denied", str(cursor))

    target = (root / Path(*parts)).resolve()
    if target != root and root not in target.parents:
        raise PrivateAccessError("escapes_root", str(target))
    if not target.exists():
        raise PrivateAccessError("not_found", str(target))
    return target


def read_private_text(private_root, requested, *, role: str, encoding: str = "utf-8") -> str:
    """经受控入口读取文本。"""
    return resolve_private(private_root, requested, role=role).read_text(encoding=encoding)
