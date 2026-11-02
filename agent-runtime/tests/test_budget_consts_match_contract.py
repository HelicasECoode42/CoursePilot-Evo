"""预算常量必须在四处保持一致。

同一个数字写在四个地方：
  - contracts/schemas/domain.schema.json 的 RunManifest const
  - api/schemas/manifest.py 的 Literal
  - application/budget.py 的 Budget 默认值
  - api/settings.py 的部署默认值

2026-10-29 把输出上限从 2000 调到 4000 时，这四处都要一起改。漏改任何一处，
写出来的 RunManifest 要么过不了契约校验，要么记录的上限和实际执行的不是一个数，
而后者不会报错——只会让运行报告说谎。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from agent_runtime.api.schemas.manifest import RunManifest
from agent_runtime.api.settings import Settings
from agent_runtime.application.budget import Budget, SessionSpendCap

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/schemas/domain.schema.json").read_text(
        encoding="utf-8"
    )
)
RUN_MANIFEST_PROPS = SCHEMA["$defs"]["RunManifest"]["properties"]


def _literal_value(field_name: str) -> int:
    annotation = RunManifest.model_fields[field_name].annotation
    values = get_args(annotation)
    assert len(values) == 1, f"{field_name} 不再是单值 Literal"
    return values[0]


def test_run_manifest_literals_match_the_contract_consts() -> None:
    for field_name in (
        "maxInputTokens",
        "maxOutputTokens",
        "maxToolCalls",
        "maxModelCalls",
        "deadlineMs",
    ):
        assert _literal_value(field_name) == RUN_MANIFEST_PROPS[field_name]["const"], (
            f"{field_name}: manifest.py 的 Literal 和 domain.schema.json 的 const 不一致"
        )


def test_budget_defaults_match_the_contract_consts() -> None:
    budget = Budget()
    assert budget.max_input_tokens == RUN_MANIFEST_PROPS["maxInputTokens"]["const"]
    assert budget.max_output_tokens == RUN_MANIFEST_PROPS["maxOutputTokens"]["const"]
    assert budget.max_tool_calls == RUN_MANIFEST_PROPS["maxToolCalls"]["const"]
    assert budget.max_model_calls == RUN_MANIFEST_PROPS["maxModelCalls"]["const"]
    assert budget.deadline_ms == RUN_MANIFEST_PROPS["deadlineMs"]["const"]


def test_deployment_defaults_match_the_budget_defaults() -> None:
    settings = Settings(service_key="k" * 32)
    budget = Budget()
    assert settings.max_input_tokens == budget.max_input_tokens
    assert settings.max_output_tokens == budget.max_output_tokens


def test_session_cap_stays_five_runs_worth() -> None:
    """会话累计上限的说明是「约可跑 5 次规划」，改单次预算时这里要跟着改。"""
    cap = SessionSpendCap()
    budget = Budget()
    assert cap.max_input_tokens == budget.max_input_tokens * 5
    assert cap.max_output_tokens == budget.max_output_tokens * 5
