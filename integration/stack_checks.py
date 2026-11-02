"""D2 集成检查公共层（第 3、4 件事的框架）：步骤定义、判定语义与失败输出格式。

判定等级（脚本、说明、PR 用同一组词）
  PASS      服务真实、状态码与结构都对 → 唯一算通过的等级
  DEGRADED  契约正确但走受控缺口（Java 未接线、无真实模型）→ 单独列出，整轮不算通过
  FAIL      服务在，但状态码、结构或语义不符契约
  BLOCKED   前置服务未就绪（缺模块、启动命令未登记、端口不通）→ 不许 SKIP 算过
  PLAN      --plan 只判定与打印，不连服务

期望值来源
  contracts/planning.openapi.json：端点与状态码集合
  contracts/schemas/domain.schema.json、agent-runtime 的 api/schemas：Envelope 与各 DTO 字段
  agent-runtime 的 routes：会话要 Bearer、planning 要 X-Request-Id 与 Idempotency-Key
  agent-runtime/README.md（W1 现状）：未配 Java → 503 TOOL_UNAVAILABLE；有目标的 planning → UNABLE_TO_VERIFY

失败输出固定五段（Issue #12 点名）：requestId / 步骤 / 期望 / 实际 / 退出码，并附复现命令；
复现命令里的会话令牌与密钥一律用占位符，不打印真值。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from stack_config import ROOT

PASS = "PASS"
DEGRADED = "DEGRADED"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
PLAN = "PLAN"
GREEN = (PASS, PLAN)

ENVELOPE_REQUIRED = ("schemaVersion", "requestId", "status", "data", "issues")
TOKEN_SLOT = "$SESSION_TOKEN"
SCHEMA_VERSION = "1.0"


def _maybe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


@dataclass
class Response:
    """一次 HTTP 往返的结果；连接层失败折算成 status=0，把原因留在 error 里。"""

    status: int
    payload: Any = None
    error: str = ""
    raw: str = ""

    @property
    def issue_codes(self) -> list[str]:
        if not isinstance(self.payload, dict):
            return []
        issues = self.payload.get("issues")
        if not isinstance(issues, list):
            return []
        return [i.get("code", "") for i in issues if isinstance(i, dict)]

    @property
    def envelope_status(self) -> str | None:
        if not isinstance(self.payload, dict):
            return None
        value = self.payload.get("status")
        return value if isinstance(value, str) else None

    @property
    def request_id(self) -> str:
        if not isinstance(self.payload, dict):
            return "-"
        value = self.payload.get("requestId")
        return value if isinstance(value, str) and value else "-"

    def describe(self) -> str:
        if self.status == 0:
            return f"连接失败（{self.error or '未知原因'}）"
        codes = "/".join(self.issue_codes) or "无 issue"
        head = self.raw.strip().replace("\n", " ")[:160] or "空响应"
        return f"HTTP {self.status}；Envelope.status={self.envelope_status}；issues={codes}；{head}"


class Transport(Protocol):
    def request(self, method: str, url: str, headers: dict[str, str], body: Any = None) -> Response: ...


class UrllibTransport:
    """真实 HTTP 传输（标准库，无第三方依赖）。"""

    # 必须大于服务自己的运行预算（docs/04 第 3 节：总 45 秒）。客户端先超时的话，
    # 一次合规的慢响应会被折算成 status=0「服务未响应」判 FAIL——实测真模型规划
    # 约 4-5 秒，但偶发更久时 10 秒会被掐断。让服务的截止时间先触发、返回 504，
    # 判定才能看到真实行为。
    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def request(self, method: str, url: str, headers: dict[str, str], body: Any = None) -> Response:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        for key, value in headers.items():
            req.add_header(key, value)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return Response(resp.status, _maybe_json(raw), "", raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return Response(exc.code, _maybe_json(raw), "", raw)
        except Exception as exc:  # noqa: BLE001 — 连接被拒、超时等统一折算
            return Response(0, None, f"{type(exc).__name__}: {exc}")


@dataclass(frozen=True)
class Attempt:
    """一个可接受的期望分支。degraded=True 表示该分支契约正确但属于受控缺口。"""

    label: str
    status: int
    envelope_status: str | None = None
    issue_code: str | None = None
    degraded: bool = False


@dataclass
class StepResult:
    step: str
    verdict: str
    request_id: str
    expect: str
    actual: str
    detail: str = ""
    repro: str = ""
    matched: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "verdict": self.verdict,
            "requestId": self.request_id,
            "expect": self.expect,
            "actual": self.actual,
            "detail": self.detail,
            "repro": self.repro,
            "matched": self.matched,
        }


def envelope_problems(response: Response) -> list[str]:
    """返回 Envelope 违规原因；空列表表示结构合规（errors.py 约定每个响应都是 Envelope）。"""
    if not isinstance(response.payload, dict):
        return ["响应不是 JSON 对象，拿不到 Envelope"]
    missing = [key for key in ENVELOPE_REQUIRED if key not in response.payload]
    problems = [f"Envelope 缺字段 {key}" for key in missing]
    version = response.payload.get("schemaVersion")
    if "schemaVersion" in response.payload and version != SCHEMA_VERSION:
        problems.append(f"schemaVersion 应为 {SCHEMA_VERSION}，实际 {version!r}")
    status = response.payload.get("status")
    if status is None:
        problems.append("Envelope.status 缺失")
    return problems


def describe_attempts(attempts: list[Attempt]) -> str:
    return " 或 ".join(attempt.label for attempt in attempts)


def evaluate(
    step: str,
    request_id: str,
    expect: str,
    response: Response,
    attempts: list[Attempt],
    repro: str,
) -> StepResult:
    """按期望分支判定一次响应。结构不合规一律 FAIL，不允许当成通过。"""
    actual = response.describe()
    if response.status == 0:
        return StepResult(step, FAIL, request_id, expect, actual, detail="服务未响应，先确认它已启动", repro=repro)
    for attempt in attempts:
        if attempt.status != response.status:
            continue
        if attempt.envelope_status is not None and response.envelope_status != attempt.envelope_status:
            continue
        if attempt.issue_code is not None and attempt.issue_code not in response.issue_codes:
            continue
        problems = envelope_problems(response)
        if problems:
            return StepResult(step, FAIL, request_id, expect, actual, detail="；".join(problems), repro=repro)
        verdict = DEGRADED if attempt.degraded else PASS
        return StepResult(
            step, verdict, request_id, expect, actual, detail=attempt.label, repro=repro, matched=attempt.label
        )
    return StepResult(
        step,
        FAIL,
        request_id,
        expect,
        actual,
        detail=f"没有匹配的期望分支（可接受：{describe_attempts(attempts)}）",
        repro=repro,
    )


def format_failure(result: StepResult, exit_code: int) -> str:
    """Issue #12 点名的五段式失败块。"""
    lines = [
        f"步骤：{result.step}",
        f"requestId：{result.request_id}",
        f"期望：{result.expect}",
        f"实际：{result.actual}",
        f"退出码：{exit_code}",
    ]
    if result.detail:
        lines.append(f"判定：{result.verdict} —— {result.detail}")
    if result.repro:
        lines.append(f"复现命令：{result.repro}")
    return "\n".join(lines)


def format_failures(results: list[StepResult], exit_code_value: int) -> str:
    """把未通过项拼成五段式；同一判定与同一原因的相邻项合并成一块，避免同一原因刷十遍。"""
    green = (PASS, PLAN)
    blocks: list[str] = []
    grouped: dict[tuple[str, str], list[StepResult]] = {}
    for result in results:
        if result.verdict in green:
            continue
        grouped.setdefault((result.verdict, result.detail), []).append(result)
    for items in grouped.values():
        head = (
            items[0]
            if len(items) == 1
            else StepResult(
                "、".join(item.step for item in items),
                items[0].verdict,
                items[0].request_id,
                items[0].expect,
                items[0].actual,
                detail=items[0].detail,
                repro=items[0].repro,
            )
        )
        blocks.append(format_failure(head, exit_code_value))
    return "\n\n".join(blocks)


def summarize(results: list[StepResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
    return counts


def exit_code(results: list[StepResult]) -> int:
    """只有全部 PASS（或 --plan 的 PLAN）才返回 0；DEGRADED/FAIL/BLOCKED 都是 1。"""
    return 0 if all(result.verdict in GREEN for result in results) else 1


def repro_curl(method: str, url: str, headers: dict[str, str], body: Any = None, token: bool = False) -> str:
    """拼一条可直接粘贴的复现命令；令牌与密钥只留占位符。"""
    parts = [f"curl -i -X {method} {url}"]
    for key, value in headers.items():
        if key.lower() in ("authorization", "x-service-key", "x-admin-key"):
            value = TOKEN_SLOT if token else "$SECRET"
        parts.append(f"  -H '{key}: {value}'")
    if body is not None:
        parts.append(f"  -d '{json.dumps(body, ensure_ascii=False)}'")
    return " ".join(parts)


def load_contract_example(name: str) -> Any:
    """读 contracts/examples/ 下的公共样例，作为集成检查的请求体真源。"""
    path = Path(ROOT) / "contracts" / "examples" / name
    return json.loads(path.read_text(encoding="utf-8"))


def record_input_from_example() -> dict[str, Any]:
    """把 contracts/examples/academic-record.json 的已修课程转成 POST 的输入体。

    该样例是 AcademicRecord（输出形状，含 academicRecordId/revision/createdAt），
    而 POST /api/v1/academic-records 收的是 AcademicRecordInput，所以只取课程与来源字段。
    """
    example = load_contract_example("academic-record.json")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "curriculumSnapshotId": example["curriculumSnapshotId"],
        "completedCourses": example["completedCourses"],
        "transcriptComplete": example["transcriptComplete"],
        "sourceKind": example["sourceKind"],
    }
