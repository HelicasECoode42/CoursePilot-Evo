from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmark"))

from agent_runtime.api.settings import Settings

from real_model_baseline import load_synthetic_cases, validate_real_run_settings


def test_real_model_capture_requires_explicit_opt_in_before_any_call() -> None:
    settings = Settings(
        model_base_url="https://model.example/v1",
        model_api_key="test-key",
        model_id="configured-model",
        java_base_url="http://127.0.0.1:8081",
        service_key="test-service-key",
    )

    with pytest.raises(ValueError, match="CP_BENCHMARK_ENABLE_REAL_MODEL"):
        validate_real_run_settings(settings, enabled=None)


@pytest.mark.parametrize(
    "settings",
    [
        Settings(model_base_url="https://model.example/v1", model_api_key="k", model_id="model"),
        Settings(
            model_base_url="https://model.example/v1",
            model_api_key="k",
            model_id="model",
            java_base_url="http://127.0.0.1:8081",
            service_key="key",
            use_fake_tools=True,
        ),
        Settings(
            model_base_url="https://model.example/v1",
            model_api_key="k",
            java_base_url="http://127.0.0.1:8081",
            service_key="key",
        ),
    ],
)
def test_real_model_capture_rejects_missing_or_fake_configuration(settings: Settings) -> None:
    with pytest.raises(ValueError):
        validate_real_run_settings(settings, enabled="true")


def test_case_loader_accepts_only_synthetic_smoke_cases() -> None:
    cases = load_synthetic_cases()

    assert {case["caseId"] for case in cases} == {"SYN-001", "SYN-002"}
    assert all(case["provenance"] == "SYNTHETIC_FICTION" for case in cases)


def test_case_loader_rejects_evolution_and_held_out_inputs() -> None:
    with pytest.raises(ValueError, match="只接受"):
        load_synthetic_cases(ROOT / "benchmark" / "cases" / "evolution")
