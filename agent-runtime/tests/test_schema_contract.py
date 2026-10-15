"""Prove the Pydantic DTOs correspond to the JSON Schema.

Each repository example is validated through the matching Pydantic model:
positive examples must parse, negative examples must raise ValidationError.
This mirrors scripts/check_contracts.py but against the Python DTOs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_runtime.api.schemas import SCHEMA_DEFS

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def _cases() -> list[tuple[str, str, bool]]:
    index = json.loads((CONTRACTS / "examples" / "index.json").read_text(encoding="utf-8"))
    return [(entry["definition"], entry["file"], entry["valid"]) for entry in index]


@pytest.mark.parametrize("definition, filename, expected_valid", _cases())
def test_example_matches_schema(definition: str, filename: str, expected_valid: bool) -> None:
    model = SCHEMA_DEFS[definition]
    payload = json.loads((CONTRACTS / "examples" / filename).read_text(encoding="utf-8"))
    if expected_valid:
        model.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            model.model_validate(payload)
