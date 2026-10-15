from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_runtime.api.schemas import PlanningRequest

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


@pytest.fixture
def contracts_dir() -> Path:
    return CONTRACTS


@pytest.fixture
def planning_request() -> PlanningRequest:
    payload = json.loads(
        (CONTRACTS / "examples" / "planning-request.json").read_text(encoding="utf-8")
    )
    return PlanningRequest.model_validate(payload)
