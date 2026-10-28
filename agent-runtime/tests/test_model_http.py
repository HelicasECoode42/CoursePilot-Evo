from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agent_runtime.adapters.model_client import (
    HttpModelAdapter,
    ModelConfigError,
    ModelInvalidOutput,
    ModelTimeout,
    ModelUpstreamError,
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


def test_build_model_adapter_rejects_placeholder_when_endpoint_is_set() -> None:
    with pytest.raises(ModelConfigError):
        build_model_adapter(
            model_base_url="https://api.deepseek.com",
            model_api_key="test-key",
            model_id="DEPLOYMENT_MODEL_PLACEHOLDER",
            temperature=0.0,
            max_output_tokens=2000,
        )


def test_build_model_adapter_stays_fake_without_key() -> None:
    adapter = build_model_adapter(
        model_base_url="https://api.deepseek.com",
        model_api_key="",
        model_id="deepseek-chat",
        temperature=0.0,
        max_output_tokens=2000,
    )
    assert adapter.__class__.__name__ == "FakeModelAdapter"


def test_http_model_parses_json_items() -> None:
    structured_intent = {
        "role": "user",
        "content": 'STRUCTURED_USER_INTENT_JSON:{"priorityOrder":["GPA"]}',
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert all(message["role"] != "tool" for message in body["messages"])
        assert structured_intent in body["messages"]
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
        2000,
        transport=httpx.MockTransport(handler),
    )
    reply = adapter.generate(context=_context(), messages=[structured_intent], tool_schemas=[])
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
        2000,
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
        2000,
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
        2000,
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
        2000,
        transport=httpx.MockTransport(handler),
    )
    reply = adapter.generate(context=_context(), messages=[], tool_schemas=[])
    assert reply.items == []
    assert reply.clarify is None


def test_http_model_rate_limit_is_not_invalid_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, json={"error": "slow down"})

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        2000,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelUpstreamError) as caught:
        adapter.generate(context=_context(), messages=[], tool_schemas=[])
    assert caught.value.status_code == 429


def test_http_model_server_error_is_not_invalid_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": "down"})

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        2000,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelUpstreamError) as caught:
        adapter.generate(context=_context(), messages=[], tool_schemas=[])
    assert caught.value.status_code == 503


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
        2000,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelInvalidOutput):
        adapter.generate(context=_context(), messages=[], tool_schemas=[])


def test_http_model_sends_max_tokens_so_the_provider_truncates() -> None:
    """输出上限必须在请求里。

    BudgetTracker.record_tokens 是在调用返回之后才检查的，那时 token 已经产生并计费；
    没有 max_tokens 时单次调用的输出长度由供应商默认值决定，本服务管不到。
    """
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
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
        777,
        transport=httpx.MockTransport(handler),
    )
    adapter.generate(context=_context(), messages=[], tool_schemas=[])
    assert seen["max_tokens"] == 777, "请求体必须带 max_tokens，否则供应商侧不截断"


def test_system_prompt_spells_out_the_choice_object_shape() -> None:
    """choices 的元素形状必须写进系统提示。

    Question.choices 的元素是 {value, label} 对象。只给 "choices":[] 这个空数组示例时，
    真模型想给选项就会返回字符串数组（实测 deepseek 三次有两次如此），Question 校验失败
    抛 MODEL_INVALID_OUTPUT；docs/04 第 3 节规定不自动重试，整个规划请求就此终止。
    """
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"items":[]}'}}]},
        )

    adapter = HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        2000,
        transport=httpx.MockTransport(handler),
    )
    adapter.generate(context=_context(), messages=[], tool_schemas=[])
    system_prompt = seen["messages"][0]["content"]  # type: ignore[index]
    assert '"value"' in system_prompt and '"label"' in system_prompt
    assert "不能是字符串" in system_prompt
