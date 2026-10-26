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


def test_policy_files_set_caps_and_context_limits(tmp_path: Path) -> None:
    (tmp_path / "tool_policy.yaml").write_text(
        "tools:\n  - name: listCourses\n    max_calls: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "context_policy.yaml").write_text(
        "max_course_facts: 3\ninclude_unknowns: false\n",
        encoding="utf-8",
    )
    snapshot = HarnessLoader(tmp_path).load()
    assert snapshot.tool_caps == {"listCourses": 1}
    assert snapshot.context.max_course_facts == 3
    assert snapshot.context.max_review_notes == 10
    assert snapshot.context.include_unknowns is False


def test_shipped_harness_policy_is_applied() -> None:
    root = Path(__file__).resolve().parents[1] / "harness"
    snapshot = HarnessLoader(root).load()
    assert snapshot.tool_caps is not None
    assert snapshot.tool_caps["validatePlan"] == 2
    assert snapshot.context.max_course_facts == 20
    assert "UNKNOWN" in snapshot.strategy_text


def test_harness_loader_ignores_non_whitelisted_files(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("v1", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not part of the harness", encoding="utf-8")
    loader = HarnessLoader(tmp_path)
    snapshot = loader.load()
    assert snapshot.version.startswith("harness:")
