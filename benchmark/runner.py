"""D-F2 基线测量骨架：逐例驱动 C 的唯一 Runner，落 RunManifest、逐例记录与 RunReport。

职责边界
  本模块只做「跑一例、记账、汇总」三件事，不判断语义、不另写 Agent：
  * 被测对象只能是通过 HTTP 调用的 C 侧 /api/v1/planning，本模块不实现第二个 Agent；
  * 语义匹配由 scorer 注入，默认 keyword_matcher 是占位基线，报告里必须写明用了哪个 matcher；
  * 引用核验由 B 的 JavaVerifier 注入，未接线时逐条记 unverified，不折算成通过。

判定语义（一例一判，不互相顶替）
  PASS      HTTP 200，评分未 blocked，且答案没有占位或缺失标记
  DEGRADED  HTTP 200 但答案带 FAKE_MODEL / FAKE_TOOL / OFFERING_UNAVAILABLE 一类标记，
            只能证明链路通，不能证明真实能力
  FAIL      HTTP 200 但评分 blocked（命中 forbiddenClaims、引用核验不通过）
  BLOCKED   用例按契约构造不出请求，或上游 503 或缺依赖，本例没有有效结果
  PLAN      只登记不执行

成本口径（docs/07 第 2 节）
  Provider 没给 token 用量时记 None，不记 0、不估算；汇总另外计算「成本可用样本覆盖率」，
  覆盖率为 0 时平均值一律 None，避免把不可得读成省 token。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from scoring.scorer import ScoreReport, score

PASS = "PASS"
DEGRADED = "DEGRADED"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
PLAN = "PLAN"

#: 答案里出现这些 code 说明走的是占位实现或缺上游数据，只能算链路通。
PLACEHOLDER_CODES = ("FAKE_MODEL", "FAKE_TOOL", "OFFERING_UNAVAILABLE")

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class UnsupportedCase(Exception):
    """用例无法按契约构造请求：不是失败，是没有有效结果。"""


@dataclass
class CaseRequest:
    body: dict[str, Any]
    notes: list[str] = field(default_factory=list)


@dataclass
class CaseOutcome:
    case_id: str
    group_id: str
    status: str
    http_status: int | None = None
    decision: str | None = None
    placeholders: list[str] = field(default_factory=list)
    unknown_codes: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_calls: int | None = None
    reported_elapsed_ms: int | None = None
    measured_latency_ms: int | None = None
    score: float | None = None
    blocked: bool | None = None
    score_report: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "groupId": self.group_id,
            "status": self.status,
            "httpStatus": self.http_status,
            "decision": self.decision,
            "placeholders": self.placeholders,
            "unknownCodes": self.unknown_codes,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "toolCalls": self.tool_calls,
            "reportedElapsedMs": self.reported_elapsed_ms,
            "measuredLatencyMs": self.measured_latency_ms,
            "score": self.score,
            "blocked": self.blocked,
            "scoreReport": self.score_report,
            "notes": self.notes,
            "error": self.error,
        }


class Transport(Protocol):
    def post(self, path: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        """返回 (HTTP 状态码, 响应 JSON)。"""
        ...


class HttpTransport:
    """最小的 urllib 传输：不引入第三方 HTTP 客户端，方便在纯净检出里跑。"""

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def post(self, path: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", **headers},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(raw or "{}")
            except json.JSONDecodeError:
                return exc.code, {"_raw": raw[:400]}


def _id_ok(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_PATTERN.fullmatch(value))


def _constraints_from_desired(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 fixture 里「想选的课」折成 PIN_COURSE 硬约束。

    PIN_COURSE 是契约里唯一表达「这门课必须在方案里」的结构；courseCode 必须过契约 Id 字符集，
    过不了就如实报 Unsupported，不换成别的字段绕过去。
    """
    constraints: list[dict[str, Any]] = []
    for course in courses:
        code = course.get("courseCode")
        if not _id_ok(code):
            raise UnsupportedCase(f"fixture 的 courseCode {code!r} 不符合契约 Id 字符集，无法构造 PIN_COURSE 约束")
        constraints.append(
            {
                "kind": "PIN_COURSE",
                "courseCode": code,
                "teacherKey": None,
                "dayOfWeek": None,
                "section": None,
                "value": None,
                "sourceText": course.get("courseName") or code,
            }
        )
    return constraints


def planning_body(
    case: dict[str, Any],
    fixture: dict[str, Any],
    *,
    academic_record_id: str | None = None,
    mode: str = "SIMULATION",
) -> CaseRequest:
    """把一个题面加 fixture 折成 PlanningRequest 请求体。

    折出来的 intent 属于「题面输入」，不是标准答案：判据仍只在 gold 里。
    """
    notes: list[str] = []
    intent = fixture.get("intent")
    if isinstance(intent, dict):
        body_intent = intent
        notes.append("intent 取 fixture 的 intent 字段（题面输入）")
    elif isinstance(fixture.get("desiredCourses"), list):
        courses = fixture["desiredCourses"]
        body_intent = {
            "motives": ["SCHEDULE"],
            "priorityOrder": [],
            "hardConstraints": _constraints_from_desired(courses),
            "softPreferences": [],
            "pinnedTeacherCoursePairs": [],
            "interestTags": [],
            "careerDirectionIds": [],
        }
        notes.append("intent 由 fixture.desiredCourses 派生：每门课记为 PIN_COURSE（题面输入）")
    else:
        raise UnsupportedCase(
            "fixture 既没有 intent 也没有 desiredCourses：该用例走 academic-records 或 requirements/audit 路径，本骨架未接"
        )

    record_id = academic_record_id or fixture.get("academicRecordId")
    if not _id_ok(record_id):
        record_id = "rec-not-provided"
        notes.append("fixture 没有合法 academicRecordId，按缺资料场景用占位符 rec-not-provided（不伪造已修记录）")

    prompt = fixture.get("promptText") or case.get("userQuery") or ""
    body = {
        "schemaVersion": "1.0",
        "curriculumSnapshotId": case.get("curriculumSnapshotId"),
        "offeringSnapshotId": case.get("offeringSnapshotId") or fixture.get("offeringSnapshotId"),
        "academicRecordId": record_id,
        "mode": mode,
        "promptText": prompt,
        "intent": body_intent,
        "previousPlanId": None,
    }
    return CaseRequest(body=body, notes=notes)


def answer_text(data: dict[str, Any]) -> str:
    """把结构化答复压成一段文本，交给 scorer 的文本匹配基线。

    这一步是有损投影：接 C 的匹配器之后应改用结构化逐项判定，报告里必须写明当轮用的是哪种。
    """
    parts: list[str] = []
    for item in data.get("recommendations") or []:
        fields = [item.get("courseCode"), item.get("courseName"), item.get("reason"), item.get("explanation")]
        parts.append(" ".join(str(value) for value in fields if value))
    clarification = data.get("clarification") or {}
    if clarification.get("text"):
        parts.append(str(clarification["text"]))
    for unknown in data.get("unknowns") or []:
        if unknown.get("message"):
            parts.append(str(unknown["message"]))
    for unknown in (data.get("academicAudit") or {}).get("unknowns") or []:
        if unknown.get("message"):
            parts.append(str(unknown["message"]))
    return "\n".join(part for part in parts if part).strip()


def unknown_codes(data: dict[str, Any]) -> list[str]:
    codes = [str(item.get("code")) for item in data.get("unknowns") or [] if item.get("code")]
    codes += [
        str(item.get("code")) for item in (data.get("academicAudit") or {}).get("unknowns") or [] if item.get("code")
    ]
    return codes


def load_manifest_schema(contracts_root: Path) -> dict[str, Any]:
    """取 contracts 里的 RunManifest 定义，作为 manifest 的唯一真源。"""
    schema_path = contracts_root / "schemas" / "domain.schema.json"
    domain = json.loads(schema_path.read_text(encoding="utf-8"))
    return {"$defs": domain["$defs"], "$ref": "#/$defs/RunManifest"}


class BenchmarkRunner:
    """逐例跑完一个 case set，输出逐例记录、RunReport 与汇总。"""

    def __init__(
        self,
        transport: Transport,
        *,
        cases_root: Path,
        gold_root: Path,
        contracts_root: Path | None = None,
        matcher=None,
        java_verifier=None,
        mode: str = "SIMULATION",
        session_path: str = "/api/v1/sessions",
        planning_path: str = "/api/v1/planning",
    ) -> None:
        self.transport = transport
        self.cases_root = cases_root
        self.gold_root = gold_root
        self.contracts_root = contracts_root
        self.matcher = matcher
        self.java_verifier = java_verifier
        self.mode = mode
        self.session_path = session_path
        self.planning_path = planning_path

    # -- 读取 -------------------------------------------------------------
    def load_cases(self) -> list[dict[str, Any]]:
        return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.cases_root.glob("*.json"))]

    def load_gold(self, case_id: str) -> dict[str, Any] | None:
        path = self.gold_root / f"{case_id}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def load_fixture(self, reference: str, repo_root: Path | None = None) -> dict[str, Any]:
        """题面里的 inputFixtureRef 是仓库相对路径；允许调用方显式给 repo_root。"""
        path = Path(reference)
        if not path.is_absolute():
            bases = [repo_root] if repo_root else []
            bases += [self.cases_root.parent, self.cases_root.parents[1], self.cases_root.parents[2]]
            found = next((base / reference for base in bases if base and (base / reference).is_file()), None)
            if found is None:
                raise FileNotFoundError(f"找不到 fixture：{reference}")
            path = found
        return json.loads(path.read_text(encoding="utf-8"))

    # -- 跑 ---------------------------------------------------------------
    def _new_session(self) -> str:
        status, payload = self.transport.post(self.session_path, {}, {})
        token = (payload.get("data") or {}).get("sessionToken")
        if status != 201 or not token:
            raise RuntimeError(f"建会话失败：HTTP {status} {payload}")
        return str(token)

    def run_case(self, case: dict[str, Any], *, repo_root: Path | None = None) -> CaseOutcome:
        case_id = str(case.get("caseId") or "unknown")
        group_id = str(case.get("groupId") or "unknown")
        try:
            fixture = self.load_fixture(str(case.get("inputFixtureRef") or ""), repo_root)
            request = planning_body(case, fixture, mode=self.mode)
        except (UnsupportedCase, OSError, json.JSONDecodeError) as exc:
            return CaseOutcome(case_id, group_id, BLOCKED, error=f"{type(exc).__name__}: {exc}")

        token = self._new_session()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Request-Id": f"req-{case_id}-bench",
            "Idempotency-Key": f"idem-{case_id}-bench",
        }
        started = time.perf_counter()
        status, payload = self.transport.post(self.planning_path, request.body, headers)
        latency_ms = int((time.perf_counter() - started) * 1000)

        outcome = CaseOutcome(case_id, group_id, BLOCKED, http_status=status, notes=list(request.notes))
        outcome.measured_latency_ms = latency_ms
        if status != 200:
            issues = payload.get("issues") or []
            codes = [str(item.get("code")) for item in issues if item.get("code")]
            outcome.error = "上游拒绝或不可用：" + (", ".join(codes) or f"HTTP {status}")
            return outcome

        data = payload.get("data") or {}
        usage = data.get("usage") or {}
        outcome.decision = data.get("decision")
        outcome.unknown_codes = unknown_codes(data)
        outcome.placeholders = [code for code in outcome.unknown_codes if code in PLACEHOLDER_CODES]
        outcome.input_tokens = usage.get("inputTokens")
        outcome.output_tokens = usage.get("outputTokens")
        outcome.tool_calls = usage.get("toolCalls")
        outcome.reported_elapsed_ms = usage.get("elapsedMs")

        gold = self.load_gold(case_id)
        report: ScoreReport | None = None
        if gold is None:
            outcome.notes.append("缺少判据文件，未评分（判据在仓库外的标注目录）")
        else:
            report = score(answer_text(data), gold, matcher=self.matcher, java_verifier=self.java_verifier)
            outcome.score = report.score
            outcome.blocked = report.blocked
            outcome.score_report = report.as_dict()

        if report is not None and report.blocked:
            outcome.status = FAIL
        elif outcome.placeholders:
            outcome.status = DEGRADED
        else:
            outcome.status = PASS
        return outcome

    def run(
        self, manifest: dict[str, Any], *, repo_root: Path | None = None, plan_only: bool = False
    ) -> dict[str, Any]:
        cases = self.load_cases()
        if plan_only:
            outcomes = [CaseOutcome(str(case.get("caseId")), str(case.get("groupId")), PLAN) for case in cases]
        else:
            outcomes = [self.run_case(case, repo_root=repo_root) for case in cases]
        return {
            "manifest": manifest,
            "outcomes": outcomes,
            "report": self.build_report(manifest, outcomes),
            "summary": self.build_summary(outcomes),
        }

    # -- 汇总 -------------------------------------------------------------
    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def build_report(self, manifest: dict[str, Any], outcomes: list[CaseOutcome]) -> dict[str, Any]:
        """严格按 contracts 的 RunReport 出报告：字段一个不多一个不少。

        基线运行 decision 恒为 BASELINE；PROMOTED / REJECTED 属于晋级判决，不在本骨架里编造。
        held-out 未接入，heldOutScore 记 None。
        """
        inputs = [outcome.input_tokens for outcome in outcomes if outcome.input_tokens is not None]
        outputs = [outcome.output_tokens for outcome in outcomes if outcome.output_tokens is not None]
        calls = [outcome.tool_calls for outcome in outcomes if outcome.tool_calls is not None]
        latencies = [outcome.measured_latency_ms for outcome in outcomes if outcome.measured_latency_ms is not None]
        failures = sorted({outcome.status for outcome in outcomes if outcome.status != PASS})
        return {
            "runId": manifest["runId"],
            "harnessVersion": manifest["harnessVersion"],
            "parentVersion": manifest.get("parentVersion"),
            "decision": "BASELINE",
            "heldOutScore": None,
            "averageInputTokens": self._mean([float(value) for value in inputs]),
            "averageOutputTokens": self._mean([float(value) for value in outputs]),
            "averageToolCalls": self._mean([float(value) for value in calls]),
            "averageLatencyMs": self._mean([float(value) for value in latencies]),
            "failureCategories": failures,
        }

    def build_summary(self, outcomes: list[CaseOutcome]) -> dict[str, Any]:
        """RunReport 装不下的东西放这里：分组等权分数、成本覆盖率、每例备注。

        协议要求「平均 token 不能把 unavailable 算零，报告有效样本覆盖率」，覆盖率只能放在这个文件里，
        因为 RunReport 的字段是固定的（additionalProperties=false）。
        """
        groups: dict[str, list[float]] = {}
        for outcome in outcomes:
            if outcome.score is not None:
                groups.setdefault(outcome.group_id, []).append(outcome.score)
        group_means = {group: self._mean(values) for group, values in sorted(groups.items())}
        macro = self._mean([mean for mean in group_means.values() if mean is not None])
        all_groups = sorted({outcome.group_id for outcome in outcomes})
        comparable = bool(all_groups) and sorted(groups) == all_groups

        total = len(outcomes)
        with_input = sum(1 for outcome in outcomes if outcome.input_tokens is not None)
        with_output = sum(1 for outcome in outcomes if outcome.output_tokens is not None)
        status_counts: dict[str, int] = {}
        for outcome in outcomes:
            status_counts[outcome.status] = status_counts.get(outcome.status, 0) + 1
        return {
            "caseCount": total,
            "statusCounts": status_counts,
            "groupMeans": group_means,
            "macroScore": macro,
            "macroComparable": comparable,
            "scoredGroups": sorted(groups),
            "caseGroups": all_groups,
            "costCoverage": {
                "inputTokens": round(with_input / total, 4) if total else None,
                "outputTokens": round(with_output / total, 4) if total else None,
            },
            "matcher": getattr(
                self.matcher, "__name__", "keyword_matcher" if self.matcher is None else type(self.matcher).__name__
            ),
            "javaVerifier": self.java_verifier is not None,
            "heldOut": "未接入：held-out 与判据都在仓库外，本骨架只跑 evolution",
        }

    # -- 落盘 -------------------------------------------------------------
    def write_outputs(self, result: dict[str, Any], out_dir: Path) -> dict[str, Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = out_dir / "run-manifest.json"
        manifest_path.write_text(json.dumps(result["manifest"], ensure_ascii=False, indent=2), encoding="utf-8")
        report_path = out_dir / "run-report.json"
        report_path.write_text(json.dumps(result["report"], ensure_ascii=False, indent=2), encoding="utf-8")
        summary_path = out_dir / "summary.json"
        summary_path.write_text(json.dumps(result["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
        cases_path = out_dir / "cases.jsonl"
        with cases_path.open("w", encoding="utf-8") as handle:
            for outcome in result["outcomes"]:
                handle.write(json.dumps(outcome.as_dict(), ensure_ascii=False) + "\n")
        return {
            "manifest": manifest_path,
            "report": report_path,
            "summary": summary_path,
            "cases": cases_path,
        }


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """按 contracts 的 RunManifest 校验：缺字段就报出来，不默认补值。"""
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    ]
