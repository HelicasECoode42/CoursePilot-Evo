"""第 3、4 件事公共层的自测：钉住判定语义与失败输出格式。

不联网、不起服务：用假传输注入响应，检查「缺服务不许算过」「降级不算绿」「编造必须被抓」这几条。
契约真源是 contracts/ 与 agent-runtime 的 routes，所以这里断言的是我方脚本的判定逻辑，不是对方服务。
"""

from __future__ import annotations

import json
from pathlib import Path

from check_stack import Chain, classify_planning, step_audit, step_planning, step_record
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


def test_fake_model_recommendation_is_not_reported_as_real_pass():
    answer = planning_answer("RECOMMENDATIONS", recommendations=[{"items": [], "verification": {}}])
    answer["unknowns"] = [{"code": "FAKE_MODEL"}]
    assert classify_planning(answer)[0] == DEGRADED


def test_chain_forwards_actual_record_and_test_snapshot():
    rec = {"items": [{"courseCode": "CS101"}], "verification": {"verdict": "UNKNOWN"}}
    transport = FakeTransport(
        {
            "academic-records": Response(201, envelope(data={"academicRecordId": "session:actual"})),
            "requirements/audit": Response(200, envelope(data={})),
            "planning": Response(200, envelope(data=planning_answer("RECOMMENDATIONS", [rec]))),
        }
    )
    chain = make_chain(transport, java_ready=True)
    chain.values["CP_TEST_CURRICULUM_SNAPSHOT_ID"] = "PLAN_CS_2025"
    assert step_record(chain).verdict == PASS
    assert step_audit(chain).verdict == PASS
    assert step_planning(chain).verdict == PASS
    for _, _, _, body in transport.calls:
        assert body["curriculumSnapshotId"] == "PLAN_CS_2025"
    assert transport.calls[0][3]["sourceKind"] == "SYNTHETIC"
    assert transport.calls[1][3]["academicRecordId"] == "session:actual"
    assert transport.calls[2][3]["academicRecordId"] == "session:actual"


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


def test_no_auth_requires_401_for_both_missing_and_fake_token():
    # docs/04 第 36 行：会话过期或不存在都是 401。假令牌原来期望 404，那会把
    # 「会话失效」和「别人的记录」混成一个码；前端只认 401 才会引导重新开始。
    transport = FakeTransport(
        {
            "academic-records": [
                Response(401, envelope("UNAUTHORIZED", issues=[{"code": "UNAUTHORIZED"}])),
                Response(401, envelope("UNAUTHORIZED", issues=[{"code": "UNAUTHORIZED"}])),
            ]
        }
    )
    assert case_no_auth(make_chain(transport)).verdict == PASS
    wrong = FakeTransport({"academic-records": Response(200, envelope(data={"items": []}))})
    assert case_no_auth(make_chain(wrong)).verdict == FAIL
    # 旧行为（假令牌 404）现在必须被判失败，否则这条检查又会放过回归。
    stale = FakeTransport(
        {
            "academic-records": [
                Response(401, envelope("UNAUTHORIZED", issues=[{"code": "UNAUTHORIZED"}])),
                Response(404, envelope("NOT_FOUND", issues=[{"code": "NOT_FOUND"}])),
            ]
        }
    )
    assert case_no_auth(make_chain(stale)).verdict == FAIL


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


def test_bad_input_accepts_the_contract_invalid_input_status():
    """422 的 envelope status 用 INVALID_INPUT 也算合规。

    domain.schema.json 的 Envelope.status 枚举里 INVALID_INPUT 是合法值，网关 422 返的
    就是它。原来只接受 ERROR，会把合规实现判成失败。
    """
    transport = FakeTransport(
        {"planning": Response(422, envelope("INVALID_INPUT", issues=[{"code": "INVALID_INPUT", "message": "bad"}]))}
    )
    assert case_bad_input(make_chain(transport)).verdict == PASS


def test_smoke_cases_use_a_record_that_belongs_to_the_session():
    """java_unwired 不能拿契约样例的 record:demo 去打。

    那个 id 不属于本会话，Java 的对象级授权会正确地返回 404 NOT_VISIBLE，
    于是这条用例测的变成了授权而不是「Java 未接线」。
    """
    transport = FakeTransport({"requirements/audit": Response(200, envelope(data={}))})
    chain = make_chain(transport, java_ready=True)
    chain.record_id = "session:mine"
    case_java_unwired(chain)
    body = transport.calls[0][3]
    assert body["academicRecordId"] == "session:mine", "必须用本会话的记录 id"
    assert "record:demo" not in json.dumps(body), "不能把契约样例的 id 发出去"


def test_placeholder_model_id_with_a_real_endpoint_is_an_error():
    """配了地址和密钥却没换模型名，必须在配置校验就报 error。

    否则 api 服务会在启动时抛 ModelConfigError，判定只看到 TCP 不可达，
    真原因要去翻 runs/stack/api.log。
    """
    from stack_config import SPECS, errors, validate

    assert any(s.key == "CP_MODEL_ID" for s in SPECS), "CP_MODEL_ID 必须登记，否则 resolve 会忽略它"

    base = {s.key: (s.default or "") for s in SPECS}
    base.update(
        {
            "CP_MODEL_BASE_URL": "https://api.deepseek.com",
            "CP_MODEL_API_KEY": "k",
            "CP_MODEL_ID": "DEPLOYMENT_MODEL_PLACEHOLDER",
        }
    )
    assert any(key == "CP_MODEL_ID" for _, key, _ in errors(validate(base)))

    base["CP_MODEL_ID"] = "deepseek-chat"
    assert not any(key == "CP_MODEL_ID" for _, key, _ in errors(validate(base)))


def test_api_child_process_gets_the_model_config():
    """网关的 Settings 用 env_prefix="CP_" 读环境变量；不注入就拿不到。"""
    from start_stack import SERVICES, child_env

    api = next(s for s in SERVICES if s["name"] == "api")
    values = {
        "CP_JAVA_BASE_URL": "http://127.0.0.1:8081",
        "CP_SERVICE_KEY": "k",
        "CP_CORS_ORIGINS": "http://127.0.0.1:5173",
        "CP_MODEL_BASE_URL": "https://api.deepseek.com",
        "CP_MODEL_API_KEY": "secret",
        "CP_MODEL_ID": "deepseek-chat",
    }
    env = child_env(api, values)
    for key, expected in values.items():
        assert env[key] == expected, f"{key} 没传给 api 子进程"
