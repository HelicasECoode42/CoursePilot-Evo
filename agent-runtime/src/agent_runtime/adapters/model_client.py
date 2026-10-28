"""Controlled model client seam.

The adapter is the only place allowed to talk to the configured model endpoint
(c-agent.md section 5): a URL found in a message or review is data, never an
endpoint. W2 ships a typed fake that only proposes ids already returned by tools.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx
from pydantic import ValidationError

from agent_runtime.api.schemas import PlanItem, Question
from agent_runtime.application.context import ExecutionContext
from agent_runtime.domain.policies.candidate_guard import KnownFacts

FACTS_MESSAGE_PREFIX = "AVAILABLE_FACTS:"


class ModelInvalidOutput(RuntimeError):
    """Unusable JSON / schema-invalid candidates (-> terminal 422, no automatic retry).

    Carries the provider usage of the failed call when it is known, so the Runner
    can still charge those tokens to the budget (docs/04 section 3).
    """

    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelTimeout(RuntimeError):
    """Provider timed out or the transport failed (-> 504, retryable, no repair)."""


class ModelUpstreamError(RuntimeError):
    """Provider 429 or 5xx. Retryable system error, never an invalid payload."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class ModelConfigError(RuntimeError):
    """URL and key are set, but the model id is still the deployment placeholder."""


PLACEHOLDER_MODEL_ID = "DEPLOYMENT_MODEL_PLACEHOLDER"


@dataclass(frozen=True)
class ModelReply:
    """Provider-agnostic model result: either a clarification or candidate items."""

    clarify: Question | None = None
    items: list[PlanItem] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelAdapter(Protocol):
    """OpenAI-compatible, provider-agnostic generate entry point.

    Implementations must honour the remaining budget/timeout and must not enable
    automatic provider retries (docs/04 section 3).
    """

    def generate(
        self,
        *,
        context: ExecutionContext,
        messages: list[dict[str, str]],
        tool_schemas: list[dict],
    ) -> ModelReply: ...


def facts_from_messages(messages: list[dict[str, str]]) -> KnownFacts:
    """Read the bounded id set the runner stuffed into the last facts message."""
    for message in reversed(messages):
        content = message.get("content", "")
        if not content.startswith(FACTS_MESSAGE_PREFIX):
            continue
        raw = json.loads(content[len(FACTS_MESSAGE_PREFIX) :])
        return KnownFacts(
            course_codes=frozenset(raw.get("courseCodes", [])),
            teacher_keys=frozenset(raw.get("teacherKeys", [])),
            class_ids=frozenset(raw.get("classIds", [])),
        )
    return KnownFacts()


class FakeModelAdapter:
    """Deterministic W2 stand-in: pick tool-provided courses, never invent ids.

    This is not a real Agent. Production still needs a configured model endpoint.
    """

    def __init__(self, *, fail_times: int = 0) -> None:
        self._fail_times = fail_times

    def generate(
        self,
        *,
        context: ExecutionContext,
        messages: list[dict[str, str]],
        tool_schemas: list[dict],
    ) -> ModelReply:
        del context, tool_schemas
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ModelInvalidOutput("模型输出不是可用的候选 JSON")
        facts = facts_from_messages(messages)
        if not facts.course_codes:
            return ModelReply(items=None)
        items = [
            PlanItem(courseCode=code, teacherKey=None, classId=None)
            for code in sorted(facts.course_codes)[:3]
        ]
        return ModelReply(items=items)


class HttpModelAdapter:
    """OpenAI-compatible chat completions. Endpoint comes from settings, never from text."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_id: str,
        temperature: float,
        max_output_tokens: int,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_id = model_id
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._transport = transport

    def generate(
        self,
        *,
        context: ExecutionContext,
        messages: list[dict[str, str]],
        tool_schemas: list[dict],
    ) -> ModelReply:
        del tool_schemas
        timeout = max(0.1, min(40.0, (context.deadline - datetime.now(UTC)).total_seconds()))
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model_id,
            "temperature": self._temperature,
            # 输出上限必须在请求里，由供应商侧截断。BudgetTracker.record_tokens 是
            # 调用返回之后才检查的，那时 token 已经产生并计费，拦不住超额输出。
            "max_tokens": self._max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "只输出一个 JSON 对象，不要解释。"
                        '格式为 {"items":[{"courseCode":"...","teacherKey":null,"classId":null}]} '
                        '或 {"clarify":{"questionId":"...","text":"...",'
                        '"choices":[{"value":"...","label":"..."}],'
                        '"allowFreeText":true,"requiredFor":[]}}。'
                        # choices 的元素形状必须写出来。只给空数组示例时，模型想给选项
                        # 就会编成字符串数组，Question 校验失败 → MODEL_INVALID_OUTPUT，
                        # 而 docs/04 第 3 节规定不自动重试，于是整个请求终止。
                        "choices 的每一项都是 {value, label} 对象，不能是字符串；"
                        "没有选项时用 []。"
                        "courseCode 必须来自 AVAILABLE_FACTS。"
                    ),
                },
                *messages,
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Request-Id": context.request_id,
        }
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ModelTimeout("模型请求超时") from exc
        except httpx.HTTPError as exc:
            raise ModelTimeout("模型请求失败") from exc
        if response.status_code == 429:
            raise ModelUpstreamError("模型端点限流", status_code=429)
        if response.status_code >= 500:
            raise ModelUpstreamError("模型端点不可用", status_code=response.status_code)
        if response.status_code >= 400:
            raise ModelInvalidOutput("模型端点拒绝请求")
        try:
            payload_json = response.json()
            content = payload_json["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelInvalidOutput("模型响应缺少 content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelInvalidOutput("模型响应缺少 content")
        input_tokens, output_tokens = _usage_tokens(payload_json)
        try:
            reply = _reply_from_content(content)
        except ModelInvalidOutput as exc:
            exc.input_tokens = input_tokens
            exc.output_tokens = output_tokens
            raise
        return ModelReply(
            clarify=reply.clarify,
            items=reply.items,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _usage_tokens(payload: dict) -> tuple[int | None, int | None]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    input_tokens = prompt if isinstance(prompt, int) and prompt >= 0 else None
    output_tokens = completion if isinstance(completion, int) and completion >= 0 else None
    return input_tokens, output_tokens


def _reply_from_content(content: str) -> ModelReply:
    text = _extract_json_object(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelInvalidOutput("模型输出不是 JSON") from exc
    if not isinstance(data, dict):
        raise ModelInvalidOutput("模型输出不是 JSON 对象")
    try:
        if data.get("clarify") is not None:
            return ModelReply(clarify=Question.model_validate(data["clarify"]))
        if "items" not in data:
            raise ModelInvalidOutput("模型未给出候选")
        raw_items = data["items"]
        if raw_items == []:
            return ModelReply(items=[])
        if not isinstance(raw_items, list):
            raise ModelInvalidOutput("模型未给出候选")
        return ModelReply(items=[PlanItem.model_validate(item) for item in raw_items])
    except ValidationError as exc:
        raise ModelInvalidOutput("模型输出不符合契约") from exc


def build_model_adapter(
    *,
    model_base_url: str | None,
    model_api_key: str,
    model_id: str,
    temperature: float,
    max_output_tokens: int,
) -> FakeModelAdapter | HttpModelAdapter:
    if model_base_url and model_api_key:
        if model_id.strip() == "" or model_id == PLACEHOLDER_MODEL_ID:
            raise ModelConfigError("已配置模型地址和密钥，但 CP_MODEL_ID 仍是占位符")
        return HttpModelAdapter(
            model_base_url, model_api_key, model_id, temperature, max_output_tokens
        )
    return FakeModelAdapter()
