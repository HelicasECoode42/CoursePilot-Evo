"""受控假响应服务（D2）：给 CI 与页面行为检查提供**可重复**的上游响应。

定位与边界（输出与文档里都写清，避免误会）
  它不是真实服务，也不是 C 的模型适配器替身：只按 `contracts/schemas/domain.schema.json` 的
  `Envelope` 契约返回固定响应，用途有两个：
    a) 证明「受控响应运行可重复」（Issue #12 验收条件第 2 条）；
    b) 让浏览器检查在已知上游下把页面驱动到引导第一问。
  C 的真实行为仍由 `check_stack.py` 对真实服务验证，**不得用本服务冒充真实服务给出通过**。
  本服务不重放 C 的输入校验（那是 C 的职责），只做 Envelope 与场景切换。

场景（`--scenario`）
  degrade_unknown（默认）  有目标的规划请求返回 `UNABLE_TO_VERIFY` 且不带推荐（资料不足只答未知）
  normal                   规划请求返回一条带核验的推荐（`scope=COURSE_ONLY`、`verdict=UNKNOWN`，不编时间结论）
  tool_unavailable         audit 与 planning 返回 `503 TOOL_UNAVAILABLE`（模拟上游依赖不可用）

可重复的定义：同一（场景、方法、路径、请求体）必须得到**逐字节相同**的响应。
`requestId` 取请求头 `X-Request-Id`（缺省用固定值 `req-stub`），所以重复请求的响应完全一致；
每次请求与响应的 sha256 追加到 `runs/stack/stub/records.jsonl`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from stack_config import ROOT

RECORD_DIR = Path(ROOT) / "runs" / "stack" / "stub"
SCENARIOS = ("degrade_unknown", "normal", "tool_unavailable")
DEFAULT_REQUEST_ID = "req-stub"
SESSION_ID = "session-stub-1"
CURRICULUM_ID = "cur-stub-2024-cs"
RECORD_ID = "record-stub-1"
FIXED_NOW = "2099-01-01T00:00:00Z"


def _envelope(request_id: str, status: str, data: Any, issues: list[dict] | None = None) -> dict:
    return {
        "schemaVersion": "1.0",
        "requestId": request_id,
        "traceId": "trace-stub-1",
        "status": status,
        "data": data,
        "provenance": [],
        "issues": issues or [],
    }


def _issue(code: str, message: str, retryable: bool = False) -> dict:
    return {"code": code, "message": message, "field": None, "retryable": retryable}


def _session() -> dict:
    return {"sessionId": SESSION_ID, "sessionToken": "stub-" + "token-" * 8, "expiresAt": FIXED_NOW}


def _snapshot() -> dict:
    """页面用 ajv 按 $defs/SnapshotSummary 校验；必须有一条非 SYNTHETIC 的已发布培养方案，页面才会进入引导。"""
    return {
        "snapshotId": CURRICULUM_ID,
        "kind": "CURRICULUM",
        "state": "PUBLISHED",
        "sourceKind": "CURRICULUM_FILE",
        "termId": None,
        "createdAt": FIXED_NOW,
        "sourceValidation": "VERIFIED",
    }


def _audit_result() -> dict:
    return {
        "curriculumSnapshotId": CURRICULUM_ID,
        "academicRecordId": RECORD_ID,
        "recordRevision": 1,
        "transcriptComplete": False,
        "requirements": [],
        "suggestedCourseCodes": [],
        "unknowns": [_issue("TRANSCRIPT_INCOMPLETE", "未提供完整已修记录，缺口不得计算")],
    }


def _usage() -> dict:
    return {"inputTokens": None, "outputTokens": None, "toolCalls": 1, "elapsedMs": 1}


def _planning_answer(scenario: str) -> dict:
    base = {
        "taskId": "task-stub-1",
        "traceId": "trace-stub-1",
        "academicAudit": _audit_result(),
        "recommendations": [],
        "clarification": None,
        "unknowns": [],
        "usage": _usage(),
    }
    if scenario == "normal":
        base["decision"] = "RECOMMENDATIONS"
        base["recommendations"] = [
            {
                "planId": "plan-stub-1",
                "items": [{"courseCode": "cs-stub-1", "teacherKey": None, "classId": None}],
                "explanation": "受控假响应：只给课程层建议，不含时间结论。",
                "reviewNoteIds": [],
                "verification": {
                    "verifierResultId": "verify-stub-1",
                    "verdict": "UNKNOWN",
                    "scope": "COURSE_ONLY",
                    "curriculumSnapshotId": CURRICULUM_ID,
                    "offeringSnapshotId": None,
                    "recordRevision": 1,
                    "violations": [],
                    "unknownChecks": [_issue("NO_OFFERING_SNAPSHOT", "没有班次快照，时间不得断言")],
                    "performedChecks": ["SCHEMA"],
                    "sourceRefIds": ["ref-stub-1"],
                },
            }
        ]
        return base
    base["decision"] = "UNABLE_TO_VERIFY"
    base["unknowns"] = [_issue("PLANNING_LOOP_PENDING", "受控假响应：资料不足时只答未知")]
    return base


@dataclass
class Route:
    status: int
    body: dict


def _routes(scenario: str, request_id: str, path: str, method: str) -> Route | None:
    """返回该请求的响应；None 表示本次上游按契约不可用（503）。"""
    unavailable = scenario == "tool_unavailable"
    if path == "/api/v1/sessions" and method == "POST":
        return Route(HTTPStatus.CREATED, _envelope(request_id, "OK", _session()))
    if path == "/api/v1/curriculum-snapshots" and method == "GET":
        return Route(HTTPStatus.OK, _envelope(request_id, "OK", {"items": [_snapshot()]}))
    if path == "/api/v1/academic-records" and method == "GET":
        return Route(HTTPStatus.OK, _envelope(request_id, "OK", {"items": []}))
    if path == "/api/v1/academic-records" and method == "POST":
        if unavailable:
            return Route(
                HTTPStatus.SERVICE_UNAVAILABLE,
                _envelope(request_id, "ERROR", None, [_issue("TOOL_UNAVAILABLE", "受控假响应：上游依赖不可用")]),
            )
        body = {
            "academicRecordId": RECORD_ID,
            "revision": 1,
            "curriculumSnapshotId": CURRICULUM_ID,
            "completedCourses": [],
            "transcriptComplete": False,
            "sourceKind": "USER_IMPORT",
            "createdAt": FIXED_NOW,
        }
        return Route(HTTPStatus.CREATED, _envelope(request_id, "OK", body))
    if path == "/api/v1/requirements/audit" and method == "POST":
        if unavailable:
            return Route(
                HTTPStatus.SERVICE_UNAVAILABLE,
                _envelope(request_id, "ERROR", None, [_issue("TOOL_UNAVAILABLE", "受控假响应：上游依赖不可用")]),
            )
        return Route(HTTPStatus.OK, _envelope(request_id, "OK", _audit_result()))
    if path == "/api/v1/planning" and method == "POST":
        if unavailable:
            return Route(
                HTTPStatus.SERVICE_UNAVAILABLE,
                _envelope(request_id, "ERROR", None, [_issue("TOOL_UNAVAILABLE", "受控假响应：上游依赖不可用")]),
            )
        return Route(HTTPStatus.OK, _envelope(request_id, "OK", _planning_answer(scenario)))
    return None


@dataclass
class StubState:
    scenario: str
    records_path: Path = field(default_factory=lambda: RECORD_DIR / "records.jsonl")

    def record(self, method: str, path: str, request_body: bytes, status: int, response_body: bytes) -> None:
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "scenario": self.scenario,
            "method": method,
            "path": path,
            "requestSha256": hashlib.sha256(request_body).hexdigest()[:16],
            "status": status,
            "responseSha256": hashlib.sha256(response_body).hexdigest()[:16],
        }
        with self.records_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def make_handler(state: StubState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            return

        def _respond(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle(self, method: str) -> None:
            request_id = self.headers.get("X-Request-Id") or DEFAULT_REQUEST_ID
            path = self.path.split("?")[0]
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            payload: dict = _envelope(
                request_id, "UNAUTHORIZED", None, [_issue("UNAUTHORIZED", "缺少或非法的会话令牌")]
            )
            status: int = HTTPStatus.UNAUTHORIZED
            if path == "/api/v1/sessions" or (self.headers.get("Authorization") or "").startswith("Bearer "):
                route = _routes(state.scenario, request_id, path, method)
                if route is None:
                    payload = _envelope(request_id, "NOT_FOUND", None, [_issue("NOT_FOUND", "受控假响应没有这个端点")])
                    status = HTTPStatus.NOT_FOUND
                else:
                    payload, status = route.body, route.status
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            # 先落记录再回包：否则客户端可能在记录写入前就拿到响应，读记录时会缺最后一条
            state.record(method, path, raw, status, body)
            self._respond(status, body)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

    return Handler


def serve(
    port: int = 8099, scenario: str = "degrade_unknown", host: str = "127.0.0.1"
) -> tuple[ThreadingHTTPServer, str, StubState]:
    """起一个受控假响应服务并返回 (server, base_url, state)；调用方负责 server.shutdown()。"""
    state = StubState(scenario=scenario)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    return server, f"http://{host}:{server.server_address[1]}", state


def serve_in_thread(
    port: int = 0, scenario: str = "degrade_unknown"
) -> tuple[ThreadingHTTPServer, str, threading.Thread, StubState]:
    """自测用：后台线程起服务，端口传 0 由系统分配。"""
    server, url, state = serve(port=port, scenario=scenario)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, url, thread, state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="D2 受控假响应服务（不是真实服务）")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--scenario", choices=SCENARIOS, default="degrade_unknown")
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args(argv)

    server, url, _state = serve(port=args.port, scenario=args.scenario, host=args.host)
    print(f"受控假响应服务已启动：{url}（场景 {args.scenario}）")
    print("边界：不是真实服务，不得用它冒充 C 的服务给出「通过」；记录写到 runs/stack/stub/records.jsonl")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止。")
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
