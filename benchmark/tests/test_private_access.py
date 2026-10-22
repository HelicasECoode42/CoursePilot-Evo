"""隔离测试（D1-T10）：Evolver 不得读取 gold / held-out / 私有评分资产。

只测受控入口这一条通道：能读到什么、读不到什么、用什么手段也读不到。
不测「同进程直接 open()」，那是进程与权限边界的事（见 private_access.py 顶部说明）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from private_access import PrivateAccessError, read_private_text, resolve_private


@pytest.fixture
def private_root(tmp_path):
    """在工作区外造一份假的私有资产 + 一个根之外的敏感文件。"""
    root = tmp_path / "restricted"
    (root / "gold").mkdir(parents=True)
    (root / "held-out").mkdir()
    (root / "private_scores").mkdir()
    (root / "gold" / "G1-001.json").write_text('{"caseId": "G1-001"}', encoding="utf-8")
    (root / "held-out" / "G1-004.json").write_text('{"caseId": "G1-004"}', encoding="utf-8")
    (root / "private_scores" / "scorer.json").write_text('{"weight": 1}', encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("不应对任何角色可见", encoding="utf-8")
    return root, outside


def test_runner_reads_gold(private_root):
    root, _ = private_root
    p = resolve_private(root, "gold/G1-001.json", role="runner")
    assert p.name == "G1-001.json"
    assert "G1-001" in read_private_text(root, "gold/G1-001.json", role="runner")


def test_runner_reads_held_out(private_root):
    root, _ = private_root
    assert resolve_private(root, "held-out/G1-004.json", role="runner").is_file()


def test_evolver_cannot_read_gold(private_root):
    root, _ = private_root
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "gold/G1-001.json", role="evolver")
    assert e.value.reason == "role_denied"
    assert "evolver" in str(e.value)


def test_evolver_cannot_read_held_out(private_root):
    root, _ = private_root
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "held-out/G1-004.json", role="evolver")
    assert e.value.reason == "role_denied"


def test_evolver_cannot_read_private_scores(private_root):
    root, _ = private_root
    with pytest.raises(PrivateAccessError):
        resolve_private(root, "private_scores/scorer.json", role="evolver")


def test_unknown_role_rejected(private_root):
    root, _ = private_root
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "gold/G1-001.json", role="admin")
    assert e.value.reason == "unknown_role"


def test_path_traversal_rejected(private_root):
    root, _ = private_root
    for bad in ("gold/../private_scores/scorer.json", "../outside/secret.txt", "gold/../../outside/secret.txt"):
        with pytest.raises(PrivateAccessError) as e:
            resolve_private(root, bad, role="runner")
        assert e.value.reason == "path_traversal", bad


def test_absolute_path_rejected(private_root):
    root, outside = private_root
    for bad in (str(outside / "secret.txt"), str(root / "gold" / "G1-001.json")):
        with pytest.raises(PrivateAccessError) as e:
            resolve_private(root, bad, role="runner")
        assert e.value.reason == "absolute_path", bad


def test_undeclared_subdir_rejected(private_root):
    root, _ = private_root
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "private_scores/scorer.json", role="runner")
    assert e.value.reason == "subdir_denied"


def test_case_variant_rejected(private_root):
    """大小写不敏感的文件系统上，GOLD/ 会命中 gold/；按原名比对必须拒绝。"""
    root, _ = private_root
    for bad in ("GOLD/G1-001.json", "Gold/G1-001.json", "HELD-OUT/G1-004.json"):
        with pytest.raises(PrivateAccessError) as e:
            resolve_private(root, bad, role="runner")
        assert e.value.reason == "subdir_denied", bad


def test_symlink_escape_rejected(private_root):
    root, outside = private_root
    link = root / "gold" / "escape.json"
    try:
        os.symlink(outside / "secret.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接（需要权限或开发者模式）")
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "gold/escape.json", role="runner")
    assert e.value.reason in ("escapes_root", "symlink_denied")


def test_symlink_inside_root_also_rejected(private_root):
    root, _ = private_root
    link = root / "gold" / "inner.json"
    try:
        os.symlink(root / "held-out" / "G1-004.json", link)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "gold/inner.json", role="runner")
    assert e.value.reason == "symlink_denied"


def test_bad_request_rejected(private_root):
    root, _ = private_root
    for bad in ("", "   ", None, 123, b"gold/G1-001.json"):
        with pytest.raises(PrivateAccessError) as e:
            resolve_private(root, bad, role="runner")  # type: ignore[arg-type]
        assert e.value.reason == "bad_request", repr(bad)


def test_missing_file_rejected(private_root):
    root, _ = private_root
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "gold/not-there.json", role="runner")
    assert e.value.reason == "not_found"


def test_missing_root_rejected(tmp_path):
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(tmp_path / "no-such-root", "gold/G1-001.json", role="runner")
    assert e.value.reason == "not_found"


def test_author_may_read_fixtures_but_runner_may_not(private_root):
    root, _ = private_root
    if not (root / "fixtures").exists():
        (root / "fixtures").mkdir()
        (root / "fixtures" / "G1-001.json").write_text("{}", encoding="utf-8")
    assert resolve_private(root, "fixtures/G1-001.json", role="author").is_file()
    with pytest.raises(PrivateAccessError) as e:
        resolve_private(root, "fixtures/G1-001.json", role="runner")
    assert e.value.reason == "subdir_denied"
