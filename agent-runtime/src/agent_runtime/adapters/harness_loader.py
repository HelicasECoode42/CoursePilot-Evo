"""Loads the whitelisted Harness files and freezes their content hash.

The same files also change a run: ``tool_policy.yaml`` caps each tool,
``context_policy.yaml`` caps what is copied into the model prompt, and
``AGENTS.md`` plus ``skills/*.md`` are that prompt's strategy text. They are
still never imported or exec'd. Budget numbers are not in this whitelist
(docs/07: the evolver must not change the budget).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# The runnable Harness whitelist (c-agent.md section 5). The root AGENTS.md is a
# developer convention and is intentionally NOT part of this list.
WHITELIST = ("AGENTS.md", "skills", "tool_policy.yaml", "context_policy.yaml")

# Strategy text is copied into the system prompt. Cap it so a patched skill
# cannot consume the whole input-token budget by itself.
_STRATEGY_LIMIT = 6000


@dataclass(frozen=True)
class ContextLimits:
    """How many facts may be copied into one model prompt."""

    max_course_facts: int = 20
    max_review_notes: int = 10
    max_offerings: int = 20
    include_unknowns: bool = True


@dataclass(frozen=True)
class HarnessSnapshot:
    version: str
    root: Path
    # None: this snapshot was built in a test and carries no tool policy.
    # {}: the policy file allows no tools. A non-empty map is the per-tool cap.
    tool_caps: dict[str, int] | None = None
    context: ContextLimits = field(default_factory=ContextLimits)
    strategy_text: str = ""


class HarnessLoader:
    """Files are policy text / controlled config, never import'ed or exec'd.

    ``version`` is a stable hash over the whitelist contents, recorded as
    ``harnessVersion`` in traces and run manifests.
    """

    def __init__(self, harness_dir: Path) -> None:
        self._harness_dir = harness_dir

    def load(self) -> HarnessSnapshot:
        files = self._collect()
        digest = hashlib.sha256()
        for path in files:
            relative = path.relative_to(self._harness_dir).as_posix().encode()
            digest.update(relative)
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        version = f"harness:{digest.hexdigest()[:16]}"
        return HarnessSnapshot(
            version=version,
            root=self._harness_dir,
            tool_caps=self._tool_caps(),
            context=self._context_limits(),
            strategy_text=self._strategy_text(),
        )

    def _tool_caps(self) -> dict[str, int] | None:
        path = self._harness_dir / "tool_policy.yaml"
        if not path.is_file():
            return None
        data = _load_mapping(path)
        tools = data.get("tools", [])
        if not isinstance(tools, list):
            raise ValueError(f"{path.name}: tools 必须是列表")
        caps: dict[str, int] = {}
        for item in tools:
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}: 每一项都要有 name 和 max_calls")
            name = item.get("name")
            calls = item.get("max_calls")
            if not isinstance(name, str) or not name or name in caps:
                raise ValueError(f"{path.name}: 工具名缺失或重复")
            if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
                raise ValueError(f"{path.name}: {name} 的 max_calls 必须是非负整数")
            caps[name] = calls
        return caps

    def _context_limits(self) -> ContextLimits:
        path = self._harness_dir / "context_policy.yaml"
        if not path.is_file():
            return ContextLimits()
        data = _load_mapping(path)
        nested = data.get("context")
        if isinstance(nested, dict):
            data = {**nested, **{key: value for key, value in data.items() if key != "context"}}
        defaults = ContextLimits()
        return ContextLimits(
            max_course_facts=_limit(data, "max_course_facts", defaults.max_course_facts),
            max_review_notes=_limit(data, "max_review_notes", defaults.max_review_notes),
            max_offerings=_limit(data, "max_offerings", defaults.max_offerings),
            include_unknowns=_flag(data, "include_unknowns", defaults.include_unknowns),
        )

    def _strategy_text(self) -> str:
        chunks: list[str] = []
        agents = self._harness_dir / "AGENTS.md"
        if agents.is_file():
            chunks.append(agents.read_text(encoding="utf-8").strip())
        skills = self._harness_dir / "skills"
        if skills.is_dir():
            for path in sorted(skills.rglob("*.md")):
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    chunks.append(text)
        combined = "\n\n".join(chunk for chunk in chunks if chunk)
        if len(combined) <= _STRATEGY_LIMIT:
            return combined
        mark = "\n……[策略文本已截断]"
        return combined[: _STRATEGY_LIMIT - len(mark)] + mark

    def _collect(self) -> list[Path]:
        paths: list[Path] = []
        for name in WHITELIST:
            candidate = self._harness_dir / name
            if candidate.is_dir():
                paths.extend(sorted(p for p in candidate.rglob("*") if p.is_file()))
            elif candidate.is_file():
                paths.append(candidate)
        return sorted(paths)


def _load_mapping(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} 必须是映射")
    return loaded


def _limit(data: dict, key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"context_policy.yaml 的 {key} 必须是非负整数")
    return value


def _flag(data: dict, key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"context_policy.yaml 的 {key} 必须是布尔值")
    return value
