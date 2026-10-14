"""Persists sanitized traces, answers and run manifests as local JSON/JSONL."""

from __future__ import annotations

from pathlib import Path

from agent_runtime.api.schemas import PlanningAnswer, RunManifest, TraceEvent


class FileResultRepository:
    """One directory per trace. Never writes prompts, grades or secrets."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save(
        self,
        *,
        answer: PlanningAnswer,
        events: list[TraceEvent],
        manifest: RunManifest,
    ) -> Path:
        directory = self._root / answer.traceId.replace(":", "_")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "answer.json").write_text(
            answer.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (directory / "manifest.json").write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        lines = [event.model_dump_json() for event in events]
        payload = "\n".join(lines)
        if payload:
            payload += "\n"
        (directory / "events.jsonl").write_text(payload, encoding="utf-8")
        return directory
