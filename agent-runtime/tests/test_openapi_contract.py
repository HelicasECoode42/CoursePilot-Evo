"""Keep FastAPI's generated OpenAPI path params aligned with the contract.

Path templates and ``in: path`` names must stay camelCase (recordId / runId).
A matching URL with snake_case parameter names still works at runtime, but the
generated spec would drift from contracts/planning.openapi.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from agent_runtime.api.app import create_app

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
_PATH_PARAM = re.compile(r"\{([^}]+)\}")


def _path_param_names(spec: dict, path: str) -> set[str]:
    names = set(_PATH_PARAM.findall(path))
    for operation in spec["paths"][path].values():
        if not isinstance(operation, dict):
            continue
        for param in operation.get("parameters") or []:
            if isinstance(param, dict) and param.get("in") == "path":
                names.add(param["name"])
    return names


def test_generated_openapi_path_params_match_contract() -> None:
    contract = json.loads((CONTRACTS / "planning.openapi.json").read_text(encoding="utf-8"))
    generated = create_app().openapi()

    missing = sorted(path for path in contract["paths"] if path not in generated["paths"])
    assert missing == [], missing

    for path in contract["paths"]:
        expected = _path_param_names(contract, path)
        actual = _path_param_names(generated, path)
        assert actual == expected, (path, actual, expected)
