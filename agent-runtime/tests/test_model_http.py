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
    _reply_from_content,
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


def test_model_json_preserves_course_reasons_and_exploration() -> None:
    reply = _reply_from_content(
        json.dumps(
            {
                "items": [{"courseCode": "CS101", "teacherKey": None, "classId": None}],
                "courseRationales": [
                    {"courseCode": "CS101", "reason": "学习基础", "reviewNoteIds": []}
                ],
                "explorationDirections": [
                    {"title": "科研", "description": "探索研究", "steps": ["读入门资料"]}
                ],
            }
        )
    )
    assert reply.course_rationales[0].reason == "学习基础"
    assert reply.exploration_directions[0].steps == ["读入门资料"]


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
    with pytest.raises(ModelInvalidOutput, match="不符合契约：缺少必填字段"):
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


def test_http_model_invalid_json_logs_only_finish_reason_and_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "sensitive-model-text-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": marker}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 78, "completion_tokens": 1000},
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
    with pytest.raises(ModelInvalidOutput) as caught:
        adapter.generate(context=_context(), messages=[], tool_schemas=[])

    assert caught.value.input_tokens == 78
    assert caught.value.output_tokens == 1000
    assert caught.value.diagnostics == {
        "shape": "content_string",
        "finish_reason": "length",
        "http_status": 200,
        "input_tokens": 78,
        "output_tokens": 1000,
        "parse_failure": "content_not_accepted",
    }
    assert marker not in caplog.text


@pytest.mark.parametrize(
    ("response_body", "shape", "finish_reason"),
    [
        (
            {"usage": {"prompt_tokens": 31, "completion_tokens": 7}},
            "choices_missing_or_not_list",
            None,
        ),
        (
            {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 2}},
            "choices_empty",
            None,
        ),
        (
            {
                "choices": [{"message": {"content": None}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 44, "completion_tokens": 1000},
            },
            "content_not_string",
            "length",
        ),
        (
            {
                "choices": [{"message": {"content": "  "}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 1},
            },
            "content_empty",
            "stop",
        ),
    ],
)
def test_http_model_missing_content_records_only_safe_response_metadata(
    response_body: dict[str, object],
    shape: str,
    finish_reason: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "must-never-be-logged"
    response_body["private_marker"] = marker

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=response_body)

    adapter = HttpModelAdapter(
        "https://api.example.test",
        "test-key",
        "test-model",
        0.0,
        1000,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelInvalidOutput) as caught:
        adapter.generate(context=_context(), messages=[], tool_schemas=[])

    diagnostic = caught.value.diagnostics
    assert diagnostic["shape"] == shape
    assert diagnostic.get("finish_reason") == finish_reason
    assert caught.value.input_tokens == diagnostic["input_tokens"]
    assert caught.value.output_tokens == diagnostic["output_tokens"]
    assert marker not in caplog.text


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
