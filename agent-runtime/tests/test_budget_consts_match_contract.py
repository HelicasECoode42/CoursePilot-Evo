"""Runtime budget defaults and the public manifest bounds."""

from __future__ import annotations

import json
from pathlib import Path

from agent_runtime.api.schemas.manifest import RunManifest
from agent_runtime.api.settings import Settings
from agent_runtime.application.budget import Budget, SessionSpendCap

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/schemas/domain.schema.json").read_text(
        encoding="utf-8"
    )
)
RUN_MANIFEST_PROPS = SCHEMA["$defs"]["RunManifest"]["properties"]


def test_run_manifest_budget_bounds_match_contract() -> None:
    runtime_properties = RunManifest.model_json_schema()["properties"]
    for field in (
        "maxInputTokens",
        "maxOutputTokens",
        "maxToolCalls",
        "maxModelCalls",
        "deadlineMs",
    ):
        assert runtime_properties[field]["minimum"] == RUN_MANIFEST_PROPS[field]["minimum"] == 1


def test_deployment_defaults_match_the_budget_defaults() -> None:
    settings = Settings(service_key="k" * 32)
    budget = Budget()
    assert settings.max_input_tokens == budget.max_input_tokens
    assert settings.max_output_tokens == budget.max_output_tokens
    assert settings.deadline_ms == budget.deadline_ms


def test_session_cap_stays_five_runs_worth() -> None:
    """会话累计上限的说明是「约可跑 5 次规划」，改单次预算时这里要跟着改。"""
    cap = SessionSpendCap()
    budget = Budget()
    assert cap.max_input_tokens == budget.max_input_tokens * 5
    assert cap.max_output_tokens == budget.max_output_tokens * 5
