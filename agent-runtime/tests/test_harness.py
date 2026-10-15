from __future__ import annotations

from pathlib import Path

from agent_runtime.adapters.harness_loader import HarnessLoader


def test_harness_version_changes_with_content(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("v1", encoding="utf-8")
    (tmp_path / "tool_policy.yaml").write_text("tools: []", encoding="utf-8")
    (tmp_path / "context_policy.yaml").write_text("context: {}", encoding="utf-8")
    (tmp_path / "skills").mkdir()

    loader = HarnessLoader(tmp_path)
    first = loader.load()
    assert first.version == loader.load().version

    (tmp_path / "AGENTS.md").write_text("v2", encoding="utf-8")
    assert loader.load().version != first.version


def test_harness_loader_ignores_non_whitelisted_files(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("v1", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not part of the harness", encoding="utf-8")
    loader = HarnessLoader(tmp_path)
    snapshot = loader.load()
    assert snapshot.version.startswith("harness:")
