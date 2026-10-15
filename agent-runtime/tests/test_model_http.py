from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agent_runtime.adapters.model_client import (
    HttpModelAdapter,
    ModelInvalidOutput,
    ModelTimeout,
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
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert all(message["role"] != "tool" for message in body["messages"])
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
                ],
                "usage": {"prompt_tokens": 21, "completion_tokens": 8},
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
    assert reply.input_tokens == 21
    assert reply.output_tokens == 8


def test_http_model_extracts_json_from_fenced_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "好的，候选如下\n```json\n"
                                '{"items":[{"courseCode":"MATH201",'
                                '"teacherKey":null,"classId":null}]}\n```'
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
    assert reply.items[0].courseCode == "MATH201"


def test_http_model_schema_invalid_item_is_invalid_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"items":[{}]}'}}]},
        )

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelInvalidOutput, match="不符合契约"):
        adapter.generate(context=_context(), messages=[], tool_schemas=[])


def test_http_model_timeout_is_not_invalid_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.TimeoutException("deadline")

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelTimeout):
        adapter.generate(context=_context(), messages=[], tool_schemas=[])


def test_http_model_empty_items_is_not_invalid_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"items":[]}'}}]},
        )

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        transport=httpx.MockTransport(handler),
    )
    reply = adapter.generate(context=_context(), messages=[], tool_schemas=[])
    assert reply.items == []
    assert reply.clarify is None


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
