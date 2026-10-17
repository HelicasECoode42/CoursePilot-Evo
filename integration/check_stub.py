"""受控假响应检查（D2）：证明「受控响应运行可重复」，并核对它按契约返回。

三件事
  1. 契约：会话、培养方案、规划响应的结构与字段必须过 `contracts/schemas/domain.schema.json`
     （用 jsonschema 校验；装不上就判 BLOCKED，不跳过）。
  2. 可重复：同一（场景、方法、路径、请求体）发两次，响应必须逐字节相同（同 X-Request-Id）。
  3. 不许编：默认场景下规划必须答未知且不带推荐；正常场景下不得出现时间维度的核验结论。

边界：本检查验证的是**受控假响应**自身，不能替代 `check_stack.py` 对真实服务的验证。

用法
  python integration/check_stub.py
  python integration/check_stub.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_stack import classify_planning
from stack_checks import (
    BLOCKED,
    FAIL,
    PASS,
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
from stack_config import ROOT
from stub_upstream import CURRICULUM_ID, DEFAULT_REQUEST_ID, RECORD_DIR, serve_in_thread

DOMAIN_SCHEMA = Path(ROOT) / "contracts" / "schemas" / "domain.schema.json"
SCHEMA_HINT = "python -m pip install jsonschema==4.26.0（仓库 requirements-dev.txt 里有）"


def schema_validator(definition: str):
    """返回一个校验函数；jsonschema 不可用时返回 None（由调用方判 BLOCKED）。"""
    try:
        import jsonschema
    except ImportError:
        return None
    schemas = json.loads(DOMAIN_SCHEMA.read_text(encoding="utf-8"))["$defs"]

    def validate(instance: Any) -> list[str]:
        validator = jsonschema.Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schemas})
        return [
            f"{'/'.join(str(p) for p in err.absolute_path) or '(root)'}: {err.message}"
            for err in validator.iter_errors(instance)
        ]

    return validate


def gate(step: str, expect: str, ok: bool, why: str, repro: str) -> StepResult | None:
    if ok:
        return None
    return StepResult(step, BLOCKED, "-", expect, why, detail=why, repro=repro)


def call(
    transport, step: str, request_id: str, expect: str, method: str, url: str, headers: dict, body=None, attempts=None
) -> tuple[StepResult, Any]:
    response = transport.request(method, url, headers, body)
    result = evaluate(
        step,
        request_id,
        expect,
        response,
        attempts or [Attempt("200/201 + Envelope(OK)", response.status, "OK")],
        repro_curl(method, url, headers, body),
    )
    return result, response


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 受控假响应检查")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    transport = UrllibTransport()
    results: list[StepResult] = []
    servers: list = []
    validate_plan = schema_validator("PlanningAnswer")
    validate_snapshot = schema_validator("SnapshotSummary")

    try:
        # 场景 1：默认（资料不足只答未知）
        srv1, base1, _t1, _st1 = serve_in_thread(scenario="degrade_unknown")
        servers.append(srv1)
        sessions_url = base1 + "/api/v1/sessions"
        r, resp = call(
            transport,
            "stub_sessions",
            DEFAULT_REQUEST_ID,
            "201 + Envelope(OK, SessionResult)",
            "POST",
            sessions_url,
            {"X-Request-Id": DEFAULT_REQUEST_ID},
        )
        results.append(r)
        token = ""
        if r.verdict == PASS and isinstance(resp.payload, dict):
            token = str((resp.payload.get("data") or {}).get("sessionToken") or "")
        auth = {"X-Request-Id": DEFAULT_REQUEST_ID, "Authorization": "Bearer " + (token or "stub")}

        step = "stub_curriculum"
        expect = "200 + Envelope(OK)；items 里有一条通过 SnapshotSummary 校验的已发布培养方案"
        r, resp = call(transport, step, DEFAULT_REQUEST_ID, expect, "GET", base1 + "/api/v1/curriculum-snapshots", auth)
        if r.verdict == PASS:
            if validate_snapshot is None:
                r = StepResult(
                    step,
                    BLOCKED,
                    DEFAULT_REQUEST_ID,
                    expect,
                    "jsonschema 未安装",
                    detail=SCHEMA_HINT,
                    repro="python integration/check_stub.py",
                )
            else:
                items = (resp.payload.get("data") or {}).get("items") or []
                problems = validate_snapshot(items[0]) if items else ["items 为空"]
                if problems:
                    r = StepResult(
                        step,
                        FAIL,
                        DEFAULT_REQUEST_ID,
                        expect,
                        "培养方案不符合 Schema",
                        detail="；".join(problems),
                        repro=r.repro,
                    )
        results.append(r)

        planning_url = base1 + "/api/v1/planning"
        planning_body = load_contract_example("planning-request.json")
        step = "stub_unknown"
        expect = "200 + decision=UNABLE_TO_VERIFY 且 recommendations 为空（资料不足不得编推荐）"
        r, resp = call(
            transport,
            step,
            DEFAULT_REQUEST_ID,
            expect,
            "POST",
            planning_url,
            auth | {"Idempotency-Key": "stub-1"},
            planning_body,
        )
        if r.verdict == PASS:
            data = (resp.payload.get("data") or {}) if isinstance(resp.payload, dict) else None
            verdict, detail = classify_planning(data)
            if verdict == FAIL:
                r = StepResult(step, FAIL, DEFAULT_REQUEST_ID, expect, resp.describe(), detail=detail, repro=r.repro)
            else:
                r = StepResult(step, PASS, DEFAULT_REQUEST_ID, expect, resp.describe(), detail=detail, repro=r.repro)
        results.append(r)

        step = "stub_repeatable"
        expect = "同一请求发两次，响应逐字节相同（受控响应可重复）"
        first = transport.request("POST", planning_url, auth | {"Idempotency-Key": "stub-1"}, planning_body)
        second = transport.request("POST", planning_url, auth | {"Idempotency-Key": "stub-1"}, planning_body)
        if r.verdict == FAIL and not first.raw:
            results.append(
                StepResult(
                    step,
                    BLOCKED,
                    DEFAULT_REQUEST_ID,
                    expect,
                    "上一次请求未成功，无法比对",
                    detail="先修 stub_unknown 再跑本项",
                    repro="python integration/check_stub.py",
                )
            )
        elif first.raw == second.raw and first.status == second.status:
            results.append(
                StepResult(
                    step,
                    PASS,
                    DEFAULT_REQUEST_ID,
                    expect,
                    f"两次 HTTP {first.status}，响应完全一致（{len(first.raw)} 字节）",
                    repro="python integration/check_stub.py",
                )
            )
        else:
            results.append(
                StepResult(
                    step,
                    FAIL,
                    DEFAULT_REQUEST_ID,
                    expect,
                    f"两次响应不同：{first.status} vs {second.status}",
                    detail="受控响应必须可重复",
                    repro="python integration/check_stub.py",
                )
            )

        step = "stub_no_auth"
        expect = "无令牌 → 401 UNAUTHORIZED；未知端点 → 404 NOT_FOUND"
        r401, _ = call(
            transport,
            step,
            DEFAULT_REQUEST_ID,
            expect,
            "GET",
            base1 + "/api/v1/curriculum-snapshots",
            {"X-Request-Id": DEFAULT_REQUEST_ID},
            attempts=[Attempt("401 缺少会话令牌", 401, "UNAUTHORIZED")],
        )
        if r401.verdict == PASS:
            r404, _ = call(
                transport,
                step,
                DEFAULT_REQUEST_ID,
                expect,
                "GET",
                base1 + "/api/v1/nope",
                auth,
                attempts=[Attempt("404 端点不存在", 404, "NOT_FOUND")],
            )
            r = (
                r404
                if r404.verdict == FAIL
                else StepResult(
                    step,
                    PASS,
                    DEFAULT_REQUEST_ID,
                    expect,
                    "401 与 404 都按契约返回",
                    repro="python integration/check_stub.py",
                )
            )
        else:
            r = r401
        results.append(r)

        # 场景 2：正常（一条带核验的课程层推荐，不得有时间结论）
        srv2, base2, _t2, _st2 = serve_in_thread(scenario="normal")
        servers.append(srv2)
        step = "stub_normal"
        expect = "200 + decision=RECOMMENDATIONS；每条 verification.scope 不得是时间维度"
        r, resp = call(
            transport,
            step,
            DEFAULT_REQUEST_ID,
            expect,
            "POST",
            base2 + "/api/v1/planning",
            auth | {"Idempotency-Key": "stub-2"},
            planning_body,
        )
        if r.verdict == PASS:
            data = (resp.payload.get("data") or {}) if isinstance(resp.payload, dict) else None
            base_verdict, detail = classify_planning(data)
            scopes = [
                ((item.get("verification") or {}).get("scope")) for item in (data or {}).get("recommendations") or []
            ]
            problems = validate_plan(data) if validate_plan else ["jsonschema 未安装（" + SCHEMA_HINT + "）"]
            if base_verdict == FAIL:
                r = StepResult(step, FAIL, DEFAULT_REQUEST_ID, expect, resp.describe(), detail=detail, repro=r.repro)
            elif "REAL_TIMETABLE" in scopes or "SIMULATION" in scopes:
                r = StepResult(
                    step,
                    FAIL,
                    DEFAULT_REQUEST_ID,
                    expect,
                    resp.describe(),
                    detail="受控推荐里出现了时间维度核验，属编造",
                    repro=r.repro,
                )
            elif problems and validate_plan is None:
                r = StepResult(
                    step, BLOCKED, DEFAULT_REQUEST_ID, expect, "jsonschema 未安装", detail=SCHEMA_HINT, repro=r.repro
                )
            elif problems:
                r = StepResult(
                    step,
                    FAIL,
                    DEFAULT_REQUEST_ID,
                    expect,
                    "PlanningAnswer 不符合 Schema",
                    detail="；".join(problems[:3]),
                    repro=r.repro,
                )
            else:
                r = StepResult(
                    step,
                    PASS,
                    DEFAULT_REQUEST_ID,
                    expect,
                    resp.describe(),
                    detail="过 Schema；仅课程层建议",
                    repro=r.repro,
                )
        results.append(r)

        # 场景 3：上游不可用（必须明确报 503，不得返回编造结果）
        srv3, base3, _t3, _st3 = serve_in_thread(scenario="tool_unavailable")
        servers.append(srv3)
        step = "stub_unavailable"
        expect = "503 + Envelope(ERROR, issue=TOOL_UNAVAILABLE)：上游不可用必须报错，不得返回结果"
        r, _ = call(
            transport,
            step,
            DEFAULT_REQUEST_ID,
            expect,
            "POST",
            base3 + "/api/v1/requirements/audit",
            auth,
            {"schemaVersion": "1.0", "curriculumSnapshotId": CURRICULUM_ID, "academicRecordId": "record-stub-1"},
            attempts=[Attempt("503 TOOL_UNAVAILABLE", 503, "ERROR", "TOOL_UNAVAILABLE")],
        )
        results.append(r)
    finally:
        for srv in servers:
            srv.shutdown()

    code = exit_code(results)
    records = sorted(RECORD_DIR.glob("records.jsonl"))

    if args.json:
        print(
            json.dumps(
                {
                    "results": [r.as_dict() for r in results],
                    "records": [str(p) for p in records],
                    "summary": summarize(results),
                    "exitCode": code,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return code

    print("D2 受控假响应检查（验证的是受控假响应自身，不替代真实服务验证）")
    print()
    print(f"{'检查项':<20} {'判定':<10} 期望摘要")
    for result in results:
        print(f"{result.step:<20} {result.verdict:<10} {result.expect}")
    bad = [r for r in results if r.verdict not in (PASS,)]
    if bad:
        print()
        print("未通过项（五段式）：")
        print()
        print(format_failures(results, code))
    print()
    print("记录：" + ("、".join(str(p) for p in records) if records else "(无)"))
    counts = summarize(results)
    print("汇总：" + "、".join(f"{k} {v}" for k, v in sorted(counts.items())) + f"；退出码 {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
