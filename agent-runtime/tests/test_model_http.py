from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agent_runtime.adapters.model_client import (
    HttpModelAdapter,
    ModelInvalidOutput,
    build_model_adapter,
)
from agent_runtime.application.context import ExecutionContext


def _context() -> ExecutionContext:
    return ExecutionContext(
        subject_id="subject:demo",
        request_id="req:demo",
        curriculum_snapshot_id="curr:demo",
        offering_snapshot_id=None,
        model_id="deepseek-chat",
        temperature=0.0,
        deadline=datetime.now(UTC) + timedelta(seconds=20),
        harness_version="harness:v0",
    )


def test_build_model_adapter_stays_fake_without_key() -> None:
    adapter = build_model_adapter(
        model_base_url="https://api.deepseek.com",
        model_api_key="",
        model_id="deepseek-chat",
        temperature=0.0,
    )
    assert adapter.__class__.__name__ == "FakeModelAdapter"


def test_http_model_parses_json_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"items":[{"courseCode":"CS101",'
                                '"teacherKey":null,"classId":null}]}'
                            )
                        }
                    }
                ]
            },
        )

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        transport=httpx.MockTransport(handler),
    )
    reply = adapter.generate(context=_context(), messages=[], tool_schemas=[])
    assert reply.items is not None
    assert reply.items[0].courseCode == "CS101"


def test_http_model_invalid_json_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "当然可以帮你选课"}}]},
        )

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelInvalidOutput):
        adapter.generate(context=_context(), messages=[], tool_schemas=[])
