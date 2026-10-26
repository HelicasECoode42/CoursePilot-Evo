"""D2 异常与未知覆盖（第 4 件事的框架）：四条必须被发现的异常。

四条检查（对应卡片「异常与未知覆盖」与验收条件第一条）
  java_unwired   Java 未就绪时 audit 必须是 503 TOOL_UNAVAILABLE，不得返回编造的核对结果
  no_time_claim  没有班次快照时不得断言时间无冲突：不许出现 REAL_TIMETABLE / SIMULATION 的核验结论
                 （该情形下「答未知或先澄清」才是正确行为，本检查把它判为通过）
  bad_input      违反契约的请求必须被 422 拒绝，不得 200
  no_auth        无令牌 → 401；假令牌 → 401（会话不存在或已过期，docs/04 第 36 行）；都不许 200

每条同样是「状态码 + Envelope + 语义」三层断言；任一条 FAIL 即非零退出，缺服务判 BLOCKED 后退出码也是 1。

用法
  python integration/smoke_stack.py --plan     # 只判定与打印计划，不连服务；退出码与真跑一致
  python integration/smoke_stack.py
  python integration/smoke_stack.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_stack import Chain, classify_planning, readiness, step_sessions
from stack_checks import (
    BLOCKED,
    FAIL,
    PASS,
    PLAN,
    Attempt,
    StepResult,
    UrllibTransport,
    evaluate,
    exit_code,
    format_failures,
    load_contract_example,
    repro_curl,
    summarize,
)
from stack_config import errors, resolve, validate

CASE_ORDER = ("java_unwired", "no_time_claim", "bad_input", "no_auth")


def case_java_unwired(chain: Chain) -> StepResult:
    step = "java_unwired"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/requirements/audit"
    headers = chain.headers(request_id, auth=True)
    example = load_contract_example("academic-record.json")
    body = {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": example["curriculumSnapshotId"],
        "academicRecordId": example["academicRecordId"],
    }
    if chain.java_ready:
        expect = "200 + Envelope(OK, AuditResult)（Java 已就绪，走正常分支）"
        attempts = [Attempt("200 学业核对完成", 200, "OK")]
    else:
        # Java 未就绪时，「明确报 503 TOOL_UNAVAILABLE」就是本条用例要验证的正确行为，
        # 所以判 PASS（不是 DEGRADED）：真正的缺口由 check_stack.py 的依赖判定去报，避免一处缺两处红。
        expect = "503 + Envelope(ERROR, issue=TOOL_UNAVAILABLE)；不得返回编造的核对结果"
        attempts = [Attempt("503 TOOL_UNAVAILABLE（Java 未就绪，受控缺口）", 503, "ERROR", "TOOL_UNAVAILABLE")]
    response = chain.transport.request("POST", url, headers, body)
    return evaluate(step, request_id, expect, response, attempts, repro_curl("POST", url, headers, body))


def case_no_time_claim(chain: Chain) -> StepResult:
    step = "no_time_claim"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/planning"
    headers = chain.headers(request_id, auth=True, idempotency=request_id)
    body = load_contract_example("planning-request.json")
    body["offeringSnapshotId"] = None
    expect = "无班次快照：不得断言时间无冲突（给推荐时 verification.scope 不得是 REAL_TIMETABLE / SIMULATION）"
    response = chain.transport.request("POST", url, headers, body)
    result = evaluate(
        step, request_id, expect, response, [Attempt("200 规划响应", 200, "OK")], repro_curl("POST", url, headers, body)
    )
    if result.verdict == FAIL:
        return result
    data: Any = response.payload.get("data") if isinstance(response.payload, dict) else None
    base, detail = classify_planning(data)
    if base == FAIL:
        return StepResult(step, FAIL, request_id, expect, response.describe(), detail=detail, repro=result.repro)
    for item in data.get("recommendations") or []:
        verification = item.get("verification") or {}
        if verification.get("scope") in ("REAL_TIMETABLE", "SIMULATION") and not verification.get("offeringSnapshotId"):
            return StepResult(
                step,
                FAIL,
                request_id,
                expect,
                response.describe(),
                detail="没有班次快照却给出时间维度的核验结论，属于编造排课能力",
                repro=result.repro,
            )
    return StepResult(
        step,
        PASS,
        request_id,
        expect,
        response.describe(),
        detail=detail + "；未出现时间断言",
        repro=result.repro,
    )


def case_bad_input(chain: Chain) -> StepResult:
    step = "bad_input"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/planning"
    headers = chain.headers(request_id, auth=True, idempotency=request_id)
    body = load_contract_example("invalid-block-day-with-section.json")
    expect = "422 + Envelope(ERROR, issues 非空)：违反契约的请求必须被拒绝，不得 200"
    response = chain.transport.request("POST", url, headers, body)
    result = evaluate(
        step,
        request_id,
        expect,
        response,
        [Attempt("422 契约校验拒绝", 422, "ERROR")],
        repro_curl("POST", url, headers, body),
    )
    if result.verdict == PASS and not response.issue_codes:
        return StepResult(
            step,
            FAIL,
            request_id,
            expect,
            response.describe(),
            detail="422 但 issues 为空，报不出拒绝原因",
            repro=result.repro,
        )
    return result


def case_no_auth(chain: Chain) -> StepResult:
    step = "no_auth"
    request_id = chain.next_request_id(step)
    url = chain.api + "/api/v1/academic-records"
    expect = "无令牌 → 401 UNAUTHORIZED；假令牌 → 401 UNAUTHORIZED；两者都不许 200"
    no_token = chain.transport.request("GET", url, chain.headers(request_id))
    result = evaluate(
        step,
        request_id,
        expect,
        no_token,
        [Attempt("401 缺少会话令牌", 401, "UNAUTHORIZED")],
        repro_curl("GET", url, chain.headers(request_id)),
    )
    if result.verdict == FAIL:
        return result
    fake_headers = chain.headers(request_id) | {"Authorization": "Bearer " + "x" * 64}
    fake = chain.transport.request("GET", url, fake_headers)
    fake_result = evaluate(
        step,
        request_id,
        expect,
        fake,
        [Attempt("401 会话不存在或已过期", 401, "UNAUTHORIZED")],
        repro_curl("GET", url, fake_headers, token=True),
    )
    if fake_result.verdict == FAIL:
        return fake_result
    return StepResult(
        step,
        PASS,
        request_id,
        expect,
        no_token.describe() + " / " + fake.describe(),
        detail="两种情况都按契约拒绝",
        repro=result.repro,
    )


CASES = {
    "java_unwired": case_java_unwired,
    "no_time_claim": case_no_time_claim,
    "bad_input": case_bad_input,
    "no_auth": case_no_auth,
}


def run_smoke(plan_only: bool, transport: Any = None) -> tuple[list[StepResult], dict[str, str], str | None]:
    values, _sources, _file = resolve(None)
    problems = errors(validate(values))
    if problems:
        return [], {}, f"配置校验未通过（{len(problems)} 条 error）：{problems[0][1]} {problems[0][2]}"
    states = readiness(plan_only)
    api_state = states.get("api", "MISSING")
    repro = "python integration/start_stack.py --plan"
    if api_state not in ("READY", "PLAN"):
        detail = f"服务 api 状态 {api_state}，异常冒烟无法开始（不跳过、不算过）"
        blocked = [
            StepResult(case, BLOCKED, "-", "依赖 api 服务", f"api 状态 {api_state}", detail=detail, repro=repro)
            for case in CASE_ORDER
        ]
        return blocked, states, f"api 未就绪（{api_state}）"
    if plan_only:
        planned = [
            StepResult(
                case, PLAN, "-", "见本文件顶部四条检查的说明", f"依赖 api={api_state}", detail="计划模式：不连服务"
            )
            for case in CASE_ORDER
        ]
        return planned, states, None
    chain = Chain(values, transport or UrllibTransport(), states.get("java") == "READY")
    session = step_sessions(chain)
    if session.verdict == FAIL:
        return (
            [
                StepResult(
                    session.step,
                    FAIL,
                    session.request_id,
                    session.expect,
                    session.actual,
                    detail="异常冒烟需要先建会话",
                    repro=session.repro,
                )
            ],
            states,
            None,
        )
    results = [CASES[case](chain) for case in CASE_ORDER]
    return results, states, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 异常与未知覆盖检查")
    ap.add_argument("--plan", action="store_true", help="只判定与打印计划，不连服务")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    results, states, blocked_reason = run_smoke(plan_only=args.plan)
    code = exit_code(results) if results else 1

    if args.json:
        print(
            json.dumps(
                {
                    "mode": "plan" if args.plan else "run",
                    "services": states,
                    "blocked": blocked_reason,
                    "cases": [r.as_dict() for r in results],
                    "summary": summarize(results),
                    "exitCode": code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return code

    print("D2 异常与未知覆盖检查：" + ("计划模式（不连服务）" if args.plan else "真跑"))
    print("服务就绪：" + ("、".join(f"{k}={v}" for k, v in states.items()) or "未判定"))
    print()
    print(f"{'用例':<16} {'判定':<10} 期望摘要")
    for result in results:
        print(f"{result.step:<16} {result.verdict:<10} {result.expect}")
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
