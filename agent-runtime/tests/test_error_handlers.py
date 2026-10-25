"""Failure paths through the real exception handlers (FastAPI TestClient).

ToolClient-level tests cannot catch a bug in errors.py: the Issue model is only
validated when a handler builds it. These tests raise the real exceptions from a
route and check the envelope that comes back.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_runtime.adapters.model_client import (
    ModelInvalidOutput,
    ModelTimeout,
    ModelUpstreamError,
)
from agent_runtime.adapters.tool_client import (
    ToolContractViolation,
    ToolRejected,
    ToolUnavailable,
)
from agent_runtime.api.errors import register_error_handlers


def _client(exc: BaseException) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise exc

    return TestClient(app)


def _issue(response) -> dict:
    body = response.json()
    assert body["status"] in {"ERROR", "NOT_FOUND", "FORBIDDEN"}
    assert len(body["issues"]) == 1
    return body["issues"][0]


def test_long_contract_message_is_truncated_and_marked_not_500() -> None:
    # A listOfferings answer with 11 pydantic errors easily passes 500 characters.
    # Before the fix, Issue() rejected the message inside the handler and the
    # request escaped as a 500.
    long_text = "listOfferings: off contract: " + ("field x is not valid; " * 200)
    response = _client(ToolContractViolation(long_text)).get("/boom")

    assert response.status_code == 502
    issue = _issue(response)
    assert issue["code"] == "TOOL_CONTRACT_VIOLATION"
    assert len(issue["message"]) <= 500
    assert issue["message"].endswith("[已截断]")
    # The prefix (which tool, which field) is what must survive the cut.
    assert issue["message"].startswith("listOfferings: off contract:")


def test_model_invalid_output_long_message_is_bounded() -> None:
    response = _client(ModelInvalidOutput("x" * 3000)).get("/boom")

    assert response.status_code == 422
    issue = _issue(response)
    assert issue["code"] == "MODEL_INVALID_OUTPUT"
    assert len(issue["message"]) <= 500


def test_empty_exception_message_still_yields_a_valid_issue() -> None:
    # Issue.message requires at least one character; an empty exception text must not
    # produce a 500 either.
    response = _client(ToolContractViolation("")).get("/boom")

    assert response.status_code == 502
    assert _issue(response)["message"]


def test_service_key_rejection_is_not_passed_to_the_browser_as_401() -> None:
    # A wrong X-Service-Key is our configuration, not the browser's credentials.
    # A 401 here would tell the browser it is unauthenticated.
    exc = ToolRejected("listCourses", 401, "SERVICE_KEY_INVALID", "缺少或错误的 X-Service-Key")
    response = _client(exc).get("/boom")

    assert response.status_code == 503
    issue = _issue(response)
    assert issue["code"] == "TOOL_UNAVAILABLE"
    assert issue["retryable"] is False
    assert "SERVICE_KEY_INVALID" not in issue["message"]


def test_missing_route_is_a_contract_violation_not_a_404() -> None:
    # A NOT_FOUND from Java with a route-level code means Java has not implemented the
    # endpoint, which is a version mismatch. Passing it through would look like
    # "this object does not exist".
    exc = ToolRejected("listCourses", 404, "NOT_FOUND", "no route")
    response = _client(exc).get("/boom")

    assert response.status_code == 502
    assert _issue(response)["code"] == "TOOL_CONTRACT_VIOLATION"


def test_not_visible_passes_through_as_404() -> None:
    exc = ToolRejected("getAcademicRecord", 404, "NOT_VISIBLE", "不可见")
    response = _client(exc).get("/boom")

    assert response.status_code == 404
    issue = _issue(response)
    assert issue["code"] == "NOT_VISIBLE"
    assert issue["retryable"] is False


def test_java_rate_limit_is_429_and_retryable() -> None:
    exc = ToolRejected("listOfferings", 429, "RATE_LIMITED", "slow down")
    response = _client(exc).get("/boom")

    assert response.status_code == 429
    issue = _issue(response)
    assert issue["code"] == "TOOL_RATE_LIMITED"
    assert issue["retryable"] is True


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code", "expected_retryable"),
    [
        (ToolUnavailable("listCourses"), 503, "TOOL_UNAVAILABLE", True),
        (ModelUpstreamError("限流", status_code=429), 429, "MODEL_RATE_LIMITED", True),
        (ModelUpstreamError("故障", status_code=500), 503, "MODEL_UNAVAILABLE", True),
        (ModelTimeout("超时"), 504, "MODEL_TIMEOUT", True),
        (ModelInvalidOutput("坏输出"), 422, "MODEL_INVALID_OUTPUT", False),
        (ToolContractViolation("契约"), 502, "TOOL_CONTRACT_VIOLATION", False),
        (
            ToolRejected("listCourses", 422, "INVALID_INPUT", "bad"),
            502,
            "TOOL_CONTRACT_VIOLATION",
            False,
        ),
    ],
)
def test_retryable_follows_status_not_a_fixed_flag(
    exc: BaseException, expected_status: int, expected_code: str, expected_retryable: bool
) -> None:
    response = _client(exc).get("/boom")

    assert response.status_code == expected_status
    issue = _issue(response)
    assert issue["code"] == expected_code
    assert issue["retryable"] is expected_retryable
