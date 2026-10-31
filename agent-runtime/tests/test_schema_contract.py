"""Prove the Pydantic DTOs correspond to the JSON Schema.

Each repository example is validated through the matching Pydantic model:
positive examples must parse, negative examples must raise ValidationError.
This mirrors scripts/check_contracts.py but against the Python DTOs.
"""

from __future__ import annotations

import json
from decimal import Decimal
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


def test_credit_dto_keeps_decimal_in_python_and_emits_json_number() -> None:
    course = SCHEMA_DEFS["CompletedCourse"](
        courseCode="CS101",
        earnedCredits=Decimal("3.10"),
        outcome="PASSED",
        completedTerm="2024-2025-1",
    )
    assert course.earnedCredits == Decimal("3.10")
    assert isinstance(course.model_dump(mode="python")["earnedCredits"], Decimal)
    encoded = course.model_dump(mode="json")["earnedCredits"]
    assert isinstance(encoded, (int, float)) and not isinstance(encoded, bool)
    assert encoded == 3.1
