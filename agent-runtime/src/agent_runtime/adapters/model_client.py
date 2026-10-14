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

from agent_runtime.api.schemas import PlanItem, Question
from agent_runtime.application.context import ExecutionContext
from agent_runtime.domain.policies.candidate_guard import KnownFacts

FACTS_MESSAGE_PREFIX = "AVAILABLE_FACTS:"


class ModelInvalidOutput(RuntimeError):
    """Provider returned unusable JSON / empty candidates (-> limited one repair)."""


@dataclass(frozen=True)
class ModelReply:
    """Provider-agnostic model result: either a clarification or candidate items."""

    clarify: Question | None = None
    items: list[PlanItem] | None = None


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
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_id = model_id
        self._temperature = temperature
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
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "只输出一个 JSON 对象，不要解释。"
                        '格式为 {"items":[{"courseCode":"...","teacherKey":null,"classId":null}]} '
                        '或 {"clarify":{"questionId":"...","text":"...","choices":[],'
                        '"allowFreeText":true,"requiredFor":[]}}。'
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
        except httpx.HTTPError as exc:
            raise ModelInvalidOutput("模型请求失败") from exc
        if response.status_code >= 400:
            raise ModelInvalidOutput("模型端点拒绝请求")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelInvalidOutput("模型响应缺少 content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelInvalidOutput("模型响应缺少 content")
        return _reply_from_content(content)


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


def _reply_from_content(content: str) -> ModelReply:
    text = _extract_json_object(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelInvalidOutput("模型输出不是 JSON") from exc
    if not isinstance(data, dict):
        raise ModelInvalidOutput("模型输出不是 JSON 对象")
    if data.get("clarify") is not None:
        return ModelReply(clarify=Question.model_validate(data["clarify"]))
    raw_items = data.get("items") or []
    if not raw_items:
        raise ModelInvalidOutput("模型未给出候选")
    return ModelReply(items=[PlanItem.model_validate(item) for item in raw_items])


def build_model_adapter(
    *,
    model_base_url: str | None,
    model_api_key: str,
    model_id: str,
    temperature: float,
) -> FakeModelAdapter | HttpModelAdapter:
    if model_base_url and model_api_key:
        return HttpModelAdapter(model_base_url, model_api_key, model_id, temperature)
    return FakeModelAdapter()
