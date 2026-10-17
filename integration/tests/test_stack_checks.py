"""第 3、4 件事公共层的自测：钉住判定语义与失败输出格式。

不联网、不起服务：用假传输注入响应，检查「缺服务不许算过」「降级不算绿」「编造必须被抓」这几条。
契约真源是 contracts/ 与 agent-runtime 的 routes，所以这里断言的是我方脚本的判定逻辑，不是对方服务。
"""

from __future__ import annotations

from pathlib import Path

from check_stack import Chain, classify_planning, step_record
from smoke_stack import case_bad_input, case_java_unwired, case_no_auth, case_no_time_claim
from stack_checks import (
    BLOCKED,
    DEGRADED,
    FAIL,
    PASS,
    PLAN,
    Attempt,
    Response,
    StepResult,
    envelope_problems,
    evaluate,
    exit_code,
    format_failure,
    format_failures,
    load_contract_example,
    record_input_from_example,
    repro_curl,
)

ROOT = Path(__file__).resolve().parents[1]

API = "http://127.0.0.1:8000"


class FakeTransport:
    """按 (方法, 路径后缀) 路由的假传输；没命中的路由返回 status=0，模拟连不上。"""

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls: list[tuple] = []

    def request(self, method: str, url: str, headers: dict, body=None) -> Response:
        self.calls.append((method, url, headers, body))
        suffix = url.split("/api/v1/")[-1].split("?")[0]
        value = self.routes.get((method, suffix), self.routes.get(suffix))
        if isinstance(value, list):
            return value.pop(0) if value else Response(0, None, "路由已用尽")
        if callable(value):
            return value(method, url, headers, body)
        return value if value is not None else Response(0, None, "假传输没有这条路由")


def envelope(status: str = "OK", data=None, issues=None, request_id: str = "req-1") -> dict:
    return {
        "schemaVersion": "1.0",
        "requestId": request_id,
        "status": status,
        "data": data,
        "provenance": [],
        "issues": issues or [],
    }


def planning_answer(decision: str, recommendations=None, clarification=None) -> dict:
    return {
        "taskId": "task-1",
        "traceId": "trace-1",
        "decision": decision,
        "academicAudit": {},
        "recommendations": recommendations or [],
        "clarification": clarification,
        "unknowns": [],
        "usage": {"inputTokens": None, "outputTokens": None, "toolCalls": 0, "elapsedMs": 12},
    }


def make_chain(transport, java_ready: bool = False) -> Chain:
    return Chain({"CP_API_BASE_URL": API}, transport, java_ready)


def test_envelope_problems_detects_missing_fields():
    assert envelope_problems(Response(200, {"schemaVersion": "1.0", "requestId": "r", "status": "OK"})) != []
    assert envelope_problems(Response(200, envelope())) == []


def test_evaluate_passes_only_on_contract_correct_response():
    result = evaluate("x", "req-1", "201", Response(201, envelope()), [Attempt("201", 201, "OK")], "curl ...")
    assert result.verdict == PASS


def test_evaluate_fails_when_envelope_missing_fields():
    result = evaluate("x", "req-1", "201", Response(201, {"status": "OK"}), [Attempt("201", 201, "OK")], "curl ...")
    assert result.verdict == FAIL
    assert "缺字段" in result.detail


def test_degraded_is_not_green():
    result = evaluate(
        "x",
        "req-1",
        "503",
        Response(503, envelope("ERROR", issues=[{"code": "TOOL_UNAVAILABLE", "message": "down"}])),
        [Attempt("503 TOOL_UNAVAILABLE", 503, "ERROR", "TOOL_UNAVAILABLE", degraded=True)],
        "curl ...",
    )
    assert result.verdict == DEGRADED
    assert exit_code([result]) == 1


def test_exit_code_zero_requires_every_step_pass():
    passed = StepResult("a", PASS, "req", "e", "a")
    assert exit_code([passed, StepResult("b", PLAN, "-", "e", "a")]) == 0
    for bad in (FAIL, DEGRADED, BLOCKED):
        assert exit_code([passed, StepResult("b", bad, "req", "e", "a")]) == 1


def test_blocked_never_counts_as_pass():
    assert exit_code([StepResult("sessions", BLOCKED, "-", "依赖 api 服务", "api 状态 MISSING")]) == 1


def test_failure_block_has_the_five_named_fields():
    result = StepResult("audit", FAIL, "req-9", "200", "HTTP 503", detail="x", repro="curl -i -X POST http://x")
    block = format_failure(result, 1)
    for label in ("requestId：req-9", "步骤：audit", "期望：200", "实际：HTTP 503", "退出码：1", "复现命令："):
        assert label in block


def test_repro_curl_masks_credentials():
    line = repro_curl("POST", API + "/api/v1/planning", {"Authorization": "Bearer real-token-value"}, {"a": 1})
    assert "real-token-value" not in line
    assert "Authorization:" in line


def test_classify_planning_rejects_fabricated_recommendations():
    verdict, detail = classify_planning(
        planning_answer("UNABLE_TO_VERIFY", recommendations=[{"planId": "p", "items": [1]}])
    )
    assert verdict == FAIL
    assert "伪造" in detail


def test_classify_planning_clarify_shape_is_enforced():
    assert classify_planning(planning_answer("CLARIFY"))[0] == FAIL
    ok = planning_answer(
        "CLARIFY", clarification={"questionId": "q1", "text": "要不要补习", "choices": [], "allowFreeText": True}
    )
    assert classify_planning(ok)[0] == DEGRADED


def test_classify_planning_accepts_verified_recommendations():
    rec = {
        "planId": "p1",
        "items": [{"courseCode": "CS101"}],
        "explanation": "依据 x",
        "verification": {"verdict": "VALID"},
    }
    assert classify_planning(planning_answer("RECOMMENDATIONS", recommendations=[rec]))[0] == PASS


def test_record_step_degrades_when_java_is_not_wired():
    transport = FakeTransport(
        {"academic-records": Response(503, envelope("ERROR", issues=[{"code": "TOOL_UNAVAILABLE"}]))}
    )
    result = step_record(make_chain(transport, java_ready=False))
    assert result.verdict == DEGRADED


def test_record_step_passes_when_java_returns_record():
    transport = FakeTransport({"academic-records": Response(201, envelope(data={"academicRecordId": "record-9"}))})
    chain = make_chain(transport, java_ready=True)
    assert step_record(chain).verdict == PASS
    assert chain.record_id == "record-9"


def test_no_time_claim_fails_on_fabricated_timetable():
    rec = {
        "planId": "p1",
        "items": [{"courseCode": "CS101"}],
        "explanation": "不冲突",
        "verification": {"verdict": "VALID", "scope": "REAL_TIMETABLE", "offeringSnapshotId": None},
    }
    transport = FakeTransport({"planning": Response(200, envelope(data=planning_answer("RECOMMENDATIONS", [rec])))})
    result = case_no_time_claim(make_chain(transport, java_ready=False))
    assert result.verdict == FAIL
    assert "编造" in result.detail


def test_no_time_claim_passes_on_refusal():
    transport = FakeTransport({"planning": Response(200, envelope(data=planning_answer("UNABLE_TO_VERIFY")))})
    assert case_no_time_claim(make_chain(transport, java_ready=False)).verdict == PASS


def test_bad_input_requires_422():
    ok = FakeTransport(
        {"planning": Response(422, envelope("ERROR", issues=[{"code": "VALIDATION", "message": "bad"}]))}
    )
    assert case_bad_input(make_chain(ok)).verdict == PASS
    swallowed = FakeTransport({"planning": Response(200, envelope(data=planning_answer("UNABLE_TO_VERIFY")))})
    assert case_bad_input(make_chain(swallowed)).verdict == FAIL


def test_no_auth_requires_401_then_404():
    transport = FakeTransport(
        {
            "academic-records": [
                Response(401, envelope("UNAUTHORIZED", issues=[{"code": "UNAUTHORIZED"}])),
                Response(404, envelope("NOT_FOUND", issues=[{"code": "NOT_FOUND"}])),
            ]
        }
    )
    assert case_no_auth(make_chain(transport)).verdict == PASS
    wrong = FakeTransport({"academic-records": Response(200, envelope(data={"items": []}))})
    assert case_no_auth(make_chain(wrong)).verdict == FAIL


def test_contract_examples_are_the_request_source():
    payload = record_input_from_example()
    assert payload["schemaVersion"] == "1.0"
    assert "academicRecordId" not in payload, "输入体不该带输出形状的字段"
    assert isinstance(payload["completedCourses"], list) and payload["completedCourses"]
    plan = load_contract_example("planning-request.json")
    assert plan["curriculumSnapshotId"] and "intent" in plan


def test_failures_with_same_cause_are_merged_into_one_block():
    blocked = [
        StepResult(step, BLOCKED, "-", "依赖 api 服务", "api 状态 UNREACHABLE", detail="api 未就绪")
        for step in ("a", "b", "c")
    ]
    text = format_failures(blocked, 1)
    assert text.count("退出码：1") == 1
    assert "a、b、c" in text


def test_java_unwired_passes_when_service_reports_tool_unavailable():
    transport = FakeTransport(
        {"requirements/audit": Response(503, envelope("ERROR", issues=[{"code": "TOOL_UNAVAILABLE"}]))}
    )
    result = case_java_unwired(make_chain(transport, java_ready=False))
    assert result.verdict == PASS
    fabricated = FakeTransport({"requirements/audit": Response(200, envelope(data={"requirements": []}))})
    assert case_java_unwired(make_chain(fabricated, java_ready=False)).verdict == FAIL
