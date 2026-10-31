"""D2 主链路集成检查（第 3 件事的框架）：建会话 → record → audit → planning → replan。

每一步断言三样东西：HTTP 状态码、Envelope 结构（errors.py 约定每个响应都是同一个信封）、
该步的业务字段。任一步 FAIL 或没就绪一律非零退出，缺服务不允许 SKIP 算过。

检查使用虚构契约样例。可用 CP_TEST_CURRICULUM_SNAPSHOT_ID 指定已发布的测试快照；
不指定时使用样例中的快照 ID。假模型和受控缺口判 DEGRADED，整轮不算通过。

用法
  python integration/check_stack.py --plan     # 只判定与打印计划，不连服务；退出码与真跑一致
  python integration/check_stack.py            # 真跑主链路
  python integration/check_stack.py --json
  python integration/check_stack.py --env-file path/to/stack.env
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stack_checks import (
    BLOCKED,
    DEGRADED,
    FAIL,
    PASS,
    PLAN,
    Attempt,
    Response,
    StepResult,
    UrllibTransport,
    evaluate,
    exit_code,
    format_failures,
    load_contract_example,
    record_input_from_example,
    repro_curl,
    summarize,
)
from stack_config import errors, resolve, validate
from start_stack import SERVICES, judge

STEP_ORDER = ("sessions", "record", "audit", "planning", "replan")


@dataclass
class Chain:
    """主链路的一次运行：持有配置、传输与跨步状态（会话令牌、记录号、上一轮答案）。"""

    values: dict[str, str]
    transport: Any
    java_ready: bool
    counter: int = 0
    token: str = ""
    record_id: str = ""
    answer: dict[str, Any] = field(default_factory=dict)

    @property
    def curriculum_id(self) -> str:
        # 回退到 os.environ：check_stack 的入口会把这个键注入 values，但 smoke_stack
        # 另建 Chain，stack_config.resolve 只收登记过的键，于是冒烟永远拿到契约样例里的
        # curr:demo —— 那个快照不存在，Java 返 422 SNAPSHOT_NOT_FOUND。读一次环境变量
        # 就让两个入口一致，不在各入口重复注入。
        return (
            self.values.get("CP_TEST_CURRICULUM_SNAPSHOT_ID")
            or os.environ.get("CP_TEST_CURRICULUM_SNAPSHOT_ID")
            or load_contract_example("academic-record.json")["curriculumSnapshotId"]
        )

    @property
    def api(self) -> str:
        return self.values["CP_API_BASE_URL"].rstrip("/")

    def next_request_id(self, step: str) -> str:
        self.counter += 1
        return f"d2-{step}-{self.counter}"

    def headers(self, request_id: str, *, auth: bool = False, idempotency: str = "") -> dict[str, str]:
        head = {"X-Request-Id": request_id}
        if auth:
            head["Authorization"] = "Bearer " + self.token
        if idempotency:
            head["Idempotency-Key"] = idempotency
        return head


def classify_planning(payload: Any) -> tuple[str, str]:
    """按 PlanningAnswer 的契约判一次规划响应：返回 (判定, 说明)。"""
    if not isinstance(payload, dict):
        return FAIL, "data 不是对象，拿不到 PlanningAnswer"
    required = ("taskId", "traceId", "decision", "recommendations", "unknowns", "usage")
    missing = [key for key in required if key not in payload]
    if missing:
        return FAIL, "PlanningAnswer 缺字段：" + "、".join(missing)
    decision = payload["decision"]
    recommendations = payload["recommendations"]
    if decision == "CLARIFY":
        if payload.get("clarification") is None:
            return FAIL, "decision=CLARIFY 但 clarification 为空（契约要求二者同时成立）"
        if recommendations:
            return FAIL, "decision=CLARIFY 不得同时给 recommendations"
        return DEGRADED, "先澄清、未给推荐：契约成立，但主链路没走完"
    if decision == "UNABLE_TO_VERIFY":
        if recommendations:
            return FAIL, "decision=UNABLE_TO_VERIFY 却带了推荐，属于伪造结论"
        return DEGRADED, "有目标时拒答（C 的 W1 骨架未接真实模型/Java），符合不许编的约定"
    if decision == "RECOMMENDATIONS":
        if not recommendations:
            return FAIL, "decision=RECOMMENDATIONS 但推荐为空"
        for item in recommendations:
            if not isinstance(item, dict) or "verification" not in item or "items" not in item:
                return FAIL, "推荐缺少 items/verification 字段"
        if any(isinstance(issue, dict) and issue.get("code") == "FAKE_MODEL" for issue in payload["unknowns"]):
            return DEGRADED, "规划链路返回推荐，但使用假模型，不能作为真实模型验收"
        return PASS, f"给出 {len(recommendations)} 条带核验的推荐"
    return FAIL, f"decision 取值不在契约枚举内：{decision!r}"


def step_sessions(chain: Chain) -> StepResult:
    step = "sessions"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/sessions"
    headers = chain.headers(request_id)
    expect = "201 + Envelope(OK)，data 含 sessionId/sessionToken/expiresAt"
    response: Response = chain.transport.request("POST", url, headers, None)
    result = evaluate(
        step, request_id, expect, response, [Attempt("201 建会话成功", 201, "OK")], repro_curl("POST", url, headers)
    )
    if result.verdict == PASS:
        data = response.payload.get("data") if isinstance(response.payload, dict) else None
        missing = [
            key for key in ("sessionId", "sessionToken", "expiresAt") if not isinstance(data, dict) or key not in data
        ]
        if missing:
            return StepResult(
                step, FAIL, request_id, expect, response.describe(), detail="会话 DTO 缺字段：" + "、".join(missing)
            )
        chain.token = data["sessionToken"]
    return result


def step_record(chain: Chain) -> StepResult:
    step = "record"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/academic-records"
    headers = chain.headers(request_id, auth=True, idempotency=request_id)
    body = record_input_from_example()
    body["curriculumSnapshotId"] = chain.curriculum_id
    body["sourceKind"] = "SYNTHETIC"
    expect = "201 + Envelope(OK, AcademicRecord)；Java 未接线时必须是 503 envelope=ERROR issue=TOOL_UNAVAILABLE"
    attempts = [Attempt("201 已修记录入库", 201, "OK")]
    if not chain.java_ready:
        attempts = [
            Attempt("503 TOOL_UNAVAILABLE（Java 未就绪，受控缺口）", 503, "ERROR", "TOOL_UNAVAILABLE", degraded=True)
        ]
        attempts.append(Attempt("201 已修记录入库", 201, "OK"))
    response = chain.transport.request("POST", url, headers, body)
    result = evaluate(step, request_id, expect, response, attempts, repro_curl("POST", url, headers, body))
    if result.verdict == PASS and isinstance(response.payload, dict):
        data = response.payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("academicRecordId"), str):
            chain.record_id = data["academicRecordId"]
    return result


def step_audit(chain: Chain) -> StepResult:
    step = "audit"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/requirements/audit"
    headers = chain.headers(request_id, auth=True)
    example = load_contract_example("academic-record.json")
    body = {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": chain.curriculum_id,
        "academicRecordId": chain.record_id or example["academicRecordId"],
    }
    expect = "200 + Envelope(OK, AuditResult)；Java 未接线时必须是 503 envelope=ERROR issue=TOOL_UNAVAILABLE"
    attempts = [Attempt("200 学业核对完成", 200, "OK")]
    if not chain.java_ready:
        attempts = [
            Attempt("503 TOOL_UNAVAILABLE（Java 未就绪，受控缺口）", 503, "ERROR", "TOOL_UNAVAILABLE", degraded=True),
            Attempt("200 学业核对完成", 200, "OK"),
        ]
    response = chain.transport.request("POST", url, headers, body)
    return evaluate(step, request_id, expect, response, attempts, repro_curl("POST", url, headers, body))


def _planning_call(chain: Chain, step: str, body: dict[str, Any], idempotency: str) -> tuple[StepResult, Response]:
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/planning"
    headers = chain.headers(request_id, auth=True, idempotency=idempotency)
    expect = "200 + Envelope(OK, PlanningAnswer)；decision 必须落在 RECOMMENDATIONS / CLARIFY / UNABLE_TO_VERIFY"
    response = chain.transport.request("POST", url, headers, body)
    result = evaluate(
        step, request_id, expect, response, [Attempt("200 规划响应", 200, "OK")], repro_curl("POST", url, headers, body)
    )
    if result.verdict == FAIL:
        return result, response
    verdict, detail = classify_planning(response.payload.get("data") if isinstance(response.payload, dict) else None)
    return StepResult(
        step, verdict, request_id, expect, response.describe(), detail=detail, repro=result.repro
    ), response


def step_planning(chain: Chain) -> StepResult:
    body = load_contract_example("planning-request.json")
    body["curriculumSnapshotId"] = chain.curriculum_id
    body["academicRecordId"] = chain.record_id or body["academicRecordId"]
    result, response = _planning_call(chain, "planning", body, chain.next_request_id("planning-idem"))
    if isinstance(response.payload, dict) and isinstance(response.payload.get("data"), dict):
        chain.answer = response.payload["data"]
    return result


def _replan_without_a_previous_plan(chain: Chain, step: str, request_id: str, url: str) -> StepResult:
    """没有可改的方案时，验证「别人的 planId 必须被拒」并判 DEGRADED。"""
    body = load_contract_example("planning-request.json")
    body["curriculumSnapshotId"] = chain.curriculum_id
    body["academicRecordId"] = chain.record_id or body["academicRecordId"]
    body["previousPlanId"] = "plan:not-in-this-session"
    headers = chain.headers(request_id, auth=True, idempotency=request_id)
    expect = "上一步没有产出方案：不属于本会话的 previousPlanId 必须被 404 拒绝"
    response = chain.transport.request("POST", url, headers, body)
    repro = repro_curl("POST", url, headers, body)
    result = evaluate(
        step,
        request_id,
        expect,
        response,
        [Attempt("404 方案不属于本会话", 404, "NOT_FOUND", "NOT_FOUND", degraded=True)],
        repro,
    )
    if result.verdict == FAIL:
        return result
    return StepResult(
        step,
        DEGRADED,
        request_id,
        expect,
        response.describe(),
        detail="上一步先澄清或拒答，没有方案可改；已验证他人方案 id 被 404 拒绝",
        repro=repro,
    )


def step_replan(chain: Chain) -> StepResult:
    """改条件重算一次，并验证同一次请求重复提交不会被跑第二遍（幂等）。"""
    step = "replan"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/planning"
    body = load_contract_example("planning-request.json")
    body["curriculumSnapshotId"] = chain.curriculum_id
    body["academicRecordId"] = chain.record_id or body["academicRecordId"]
    recommendations = chain.answer.get("recommendations") or []
    previous_plan_id = None
    if recommendations and isinstance(recommendations[0], dict):
        previous_plan_id = recommendations[0].get("planId")
    if not previous_plan_id:
        # 上一步先澄清或拒答时没有方案可改，重规划的正常分支本轮验证不了。
        # 这时不拿写死的假 id 去打——那个方案不属于本会话，被 404 拒掉是
        # docs/04「previousPlanId 必须属当前会话」要求的正确行为，判 FAIL 等于
        # 把正确行为报成缺陷。改为就地验证这条拒绝规则，并判 DEGRADED 说明原因。
        return _replan_without_a_previous_plan(chain, step, request_id, url)
    body["previousPlanId"] = previous_plan_id
    idempotency = request_id
    headers = chain.headers(request_id, auth=True, idempotency=idempotency)
    expect = "200 + Envelope(OK)；同 Idempotency-Key 重复提交必须返回同一份结果（不双跑）"
    first = chain.transport.request("POST", url, headers, body)
    result = evaluate(
        step, request_id, expect, first, [Attempt("200 重规划响应", 200, "OK")], repro_curl("POST", url, headers, body)
    )
    if result.verdict == FAIL:
        return result
    verdict, detail = classify_planning(first.payload.get("data") if isinstance(first.payload, dict) else None)
    second = chain.transport.request("POST", url, headers, body)
    if second.status != first.status or second.payload != first.payload:
        return StepResult(
            step,
            FAIL,
            request_id,
            expect,
            f"第二次 HTTP {second.status}；与第一次不一致",
            detail="同 Idempotency-Key 重复提交返回了不同结果（幂等失效）",
            repro=result.repro,
        )
    return StepResult(
        step,
        verdict,
        request_id,
        expect,
        first.describe(),
        detail=detail + "；重复提交命中幂等缓存，结果一致",
        repro=result.repro,
    )


RUNNERS = {
    "sessions": step_sessions,
    "record": step_record,
    "audit": step_audit,
    "planning": step_planning,
    "replan": step_replan,
}


def readiness(plan_only: bool) -> dict[str, str]:
    """各服务就绪判定；复用 start_stack 的 judge，保证两个脚本判定口径一致。"""
    values, _sources, _file = resolve(None)
    return {svc["name"]: judge(svc, values, probe=not plan_only)["status"] for svc in SERVICES}


def run_chain(plan_only: bool, transport: Any = None) -> tuple[list[StepResult], dict[str, str], str | None]:
    values, _sources, _used_file = resolve(None)
    values["CP_TEST_CURRICULUM_SNAPSHOT_ID"] = os.environ.get("CP_TEST_CURRICULUM_SNAPSHOT_ID", "")
    problems = errors(validate(values))
    if problems:
        return [], {}, f"配置校验未通过（{len(problems)} 条 error），先修配置：{problems[0][1]} {problems[0][2]}"
    states = readiness(plan_only)
    api_state = states.get("api", "MISSING")
    java_ready = states.get("java") == "READY"
    if api_state not in ("READY", "PLAN"):
        detail = f"服务 api 状态 {api_state}，主链路无法开始（不跳过、不算过）"
        repro = "python integration/start_stack.py --plan"
        blocked = [
            StepResult(step, BLOCKED, "-", "依赖 api 服务", f"api 状态 {api_state}", detail=detail, repro=repro)
            for step in STEP_ORDER
        ]
        return blocked, states, f"api 未就绪（{api_state}）"
    if plan_only:
        planned = [
            StepResult(step, PLAN, "-", "见 README 的步骤表", f"依赖 api={api_state}", detail="计划模式：不连服务")
            for step in STEP_ORDER
        ]
        return planned, states, None
    chain = Chain(values, transport or UrllibTransport(), java_ready)
    results: list[StepResult] = []
    for step in STEP_ORDER:
        result = RUNNERS[step](chain)
        results.append(result)
        if result.verdict in (FAIL, BLOCKED):
            break
    return results, states, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 主链路集成检查")
    ap.add_argument("--plan", action="store_true", help="只判定与打印计划，不连服务")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    results, states, blocked_reason = run_chain(plan_only=args.plan)
    code = exit_code(results) if results else 1

    if args.json:
        print(
            json.dumps(
                {
                    "mode": "plan" if args.plan else "run",
                    "services": states,
                    "blocked": blocked_reason,
                    "steps": [r.as_dict() for r in results],
                    "summary": summarize(results),
                    "exitCode": code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return code

    print("D2 主链路集成检查：" + ("计划模式（不连服务）" if args.plan else "真跑"))
    print("服务就绪：" + ("、".join(f"{k}={v}" for k, v in states.items()) or "未判定"))
    print()
    print(f"{'步骤':<10} {'判定':<10} 期望摘要")
    for result in results:
        print(f"{result.step:<10} {result.verdict:<10} {result.expect}")
    print()
    bad = [r for r in results if r.verdict not in (PASS, PLAN)]
    if bad:
        print("未通过项（五段式，可直接贴到 Issue）：")
        print()
        print(format_failures(results, code))
    if blocked_reason:
        print()
        print(f"阻塞：{blocked_reason}")
    counts = summarize(results)
    print()
    print("汇总：" + "、".join(f"{k} {v}" for k, v in sorted(counts.items())) + f"；退出码 {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
