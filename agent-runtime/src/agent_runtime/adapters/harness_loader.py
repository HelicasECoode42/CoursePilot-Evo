"""Loads the whitelisted Harness files and freezes their content hash."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# The runnable Harness whitelist (c-agent.md section 5). The root AGENTS.md is a
# developer convention and is intentionally NOT part of this list.
WHITELIST = ("AGENTS.md", "skills", "tool_policy.yaml", "context_policy.yaml")


@dataclass(frozen=True)
class HarnessSnapshot:
    version: str
    root: Path


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
        return HarnessSnapshot(version=version, root=self._harness_dir)

    def _collect(self) -> list[Path]:
        paths: list[Path] = []
        for name in WHITELIST:
            candidate = self._harness_dir / name
            if candidate.is_dir():
                paths.extend(sorted(p for p in candidate.rglob("*") if p.is_file()))
            elif candidate.is_file():
                paths.append(candidate)
        return sorted(paths)
