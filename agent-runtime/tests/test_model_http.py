from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agent_runtime.adapters.model_client import (
    HttpModelAdapter,
    ModelConfigError,
    ModelInvalidOutput,
    ModelOutputTruncated,
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


def test_shared_model_transport_caps_generate_and_chat_at_30_seconds() -> None:
    observed_timeouts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_timeouts.append(request.extensions["timeout"]["read"])
        messages = json.loads(request.content)["messages"]
        is_chat = "只含以下四个字段" in messages[0]["content"]
        content = (
            '{"reply":"回答","question":null,"courses":[],"suggestions":[]}'
            if is_chat
            else '{"items":[]}'
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    adapter = HttpModelAdapter(
        "https://model.test/v1",
        "test-key",
        "test-model",
        0.0,
        100,
        transport=httpx.MockTransport(handler),
    )
    context = replace(_context(), deadline=datetime.now(UTC) + timedelta(seconds=90))
    adapter.generate(context=context, messages=[], tool_schemas=[])
    adapter.generate_chat(context=context, messages=[])

    assert observed_timeouts == [30.0, 30.0]


@pytest.mark.parametrize(
    ("content_factory", "expected_path", "expected_reason"),
    [
        (lambda: "private-model-text that is not JSON", "content", "INVALID_JSON"),
        (
            lambda: json.dumps(
                {
                    "reply": "回答",
                    "question": None,
                    "courses": [
                        {
                            "courseCode": "CS101",
                            "reason": "private-model-text" * 51,
                            "reviewNoteIds": [],
                        }
                    ],
                    "suggestions": [],
                },
                ensure_ascii=False,
            ),
            "courses[0].reason",
            "STRING_LENGTH",
        ),
    ],
)
def test_advice_chat_invalid_output_logs_redacted_field_diagnostics_once(
    caplog, content_factory, expected_path, expected_reason
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": content_factory()}}],
                "usage": {"prompt_tokens": 23, "completion_tokens": 11},
            },
        )

    adapter = HttpModelAdapter(
        "https://model.test/v1",
        "test-key",
        "test-model",
        0.0,
        100,
        transport=httpx.MockTransport(handler),
    )
    caplog.set_level(logging.WARNING, logger="agent_runtime.adapters.model_client")
    with pytest.raises(ModelInvalidOutput) as caught:
        adapter.generate_chat(context=_context(), messages=[])

    assert calls == 1
    assert caught.value.input_tokens == 23
    assert caught.value.output_tokens == 11
    assert caught.value.diagnostics["request_id"] == "req:demo"
    assert caught.value.diagnostics["field_path"] == expected_path
    assert caught.value.diagnostics["reason_code"] == expected_reason
    assert caught.value.diagnostics["finish_reason"] == "stop"
    assert "private-model-text" not in caplog.text


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


def _truncating_adapter(payload: dict[str, object]) -> HttpModelAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload)

    return HttpModelAdapter(
        "https://api.deepseek.com",
        "test-key",
        "deepseek-chat",
        0.0,
        2000,
        transport=httpx.MockTransport(handler),
    )


def test_truncated_json_is_not_reported_as_invalid_output() -> None:
    """finish_reason=length 是预算截断，不是模型输出非法。

    实测 2026-10-29：真实规划两次都失败，日志是
    {"finish_reason": "length", "output_tokens": 2000, "shape": "content_string",
     "parse_failure": "content_not_accepted"}。
    output_tokens 正好顶到输出上限 2000，JSON 写到一半被切断。
    之前报成 MODEL_INVALID_OUTPUT，把人引去查提示词和 schema，
    而真正要改的是输出预算或单次回复的长度。
    """
    adapter = _truncating_adapter(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    # 合法 JSON 的开头，被截断所以解析不了。
                    "message": {"content": '{"items": [{"courseCode": "CS1'},
                }
            ],
            "usage": {"prompt_tokens": 3392, "completion_tokens": 2000},
        }
    )
    with pytest.raises(ModelOutputTruncated) as caught:
        adapter.generate(context=_context(), messages=[], tool_schemas=[])
    message = str(caught.value)
    assert "输出预算截断" in message
    # 要给出那个要改的数，不然看了也不知道改哪里。
    assert "2000" in message
    assert caught.value.output_tokens == 2000
    assert caught.value.diagnostics["finish_reason"] == "length"


def test_truncated_empty_content_is_also_truncation_not_missing_content() -> None:
    """content 为空 + finish_reason=length：同样是被截断，不是「缺少 content」。"""
    adapter = _truncating_adapter(
        {
            "choices": [{"finish_reason": "length", "message": {"content": ""}}],
            "usage": {"prompt_tokens": 3392, "completion_tokens": 2000},
        }
    )
    with pytest.raises(ModelOutputTruncated):
        adapter.generate(context=_context(), messages=[], tool_schemas=[])


def test_unparseable_json_without_length_stays_invalid_output() -> None:
    """finish_reason 不是 length 时仍然是 MODEL_INVALID_OUTPUT，分类没有被放宽。"""
    adapter = _truncating_adapter(
        {
            "choices": [{"finish_reason": "stop", "message": {"content": "not json"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }
    )
    with pytest.raises(ModelInvalidOutput) as caught:
        adapter.generate(context=_context(), messages=[], tool_schemas=[])
    assert not isinstance(caught.value, ModelOutputTruncated)
