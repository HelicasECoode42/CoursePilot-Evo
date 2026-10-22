"""held-out 隔离子进程：读题面与判据、跑一遍、只吐聚合结果。

进程内允许读判据；进程外只能看到本文件打印的最后一行 JSON，且打印前会自检不含判据原句。

环境变量
  CP_HELDOUT_CASES / CP_HELDOUT_GOLD / CP_HELDOUT_MANIFEST  必需
  CP_HELDOUT_TRANSPORT = http | dry                          默认 http；dry 供隔离自检，不发网络请求
  CP_HELDOUT_BASE_URL                                        http 模式下的网关地址

退出码
  0 正常，最后一行是 JSON；2 参数或环境不成立；1 运行失败
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "benchmark"))

from runner import BenchmarkRunner, HttpTransport, load_manifest_schema, validate_manifest


class DryTransport:
    """隔离自检用：不发网络请求，固定返回可判定的答复，形状与真实 Envelope 一致。"""

    def post(self, path, body, headers):
        if path.endswith("/sessions"):
            return 201, {"schemaVersion": "1.0", "status": "OK", "data": {"sessionToken": "dry-token"}}
        if path.endswith("/academic-records"):
            return 201, {"schemaVersion": "1.0", "status": "OK", "data": {"academicRecordId": "record:dry"}}
        if path.endswith("/requirements/audit"):
            return 200, {
                "schemaVersion": "1.0",
                "status": "OK",
                "data": {
                    "curriculumSnapshotId": "dry",
                    "academicRecordId": "record:dry",
                    "recordRevision": 1,
                    "transcriptComplete": False,
                    "requirements": [],
                    "suggestedCourseCodes": [],
                    "unknowns": [{"code": "DRY_TRANSPORT", "message": "隔离自检，未调用真实服务"}],
                },
            }
        return 200, {
            "schemaVersion": "1.0",
            "status": "OK",
            "data": {
                "decision": "CLARIFY",
                "recommendations": [],
                "clarification": {
                    "questionId": "dry",
                    "text": "隔离自检占位追问",
                    "choices": [],
                    "allowFreeText": True,
                },
                "unknowns": [{"code": "DRY_TRANSPORT", "message": "隔离自检，未调用真实服务"}],
                "usage": {"inputTokens": None, "outputTokens": None, "toolCalls": 0, "elapsedMs": 0},
            },
        }


def gold_claims(gold_root: Path) -> list[str]:
    claims: list[str] = []
    for path in sorted(gold_root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key in ("requiredFacts", "requiredUnknowns", "requiredClarification", "forbiddenClaims"):
            claims.extend(str(item) for item in payload.get(key) or [])
    return claims


def main() -> int:
    cases = os.environ.get("CP_HELDOUT_CASES")
    gold = os.environ.get("CP_HELDOUT_GOLD")
    manifest_path = os.environ.get("CP_HELDOUT_MANIFEST")
    if not cases or not gold or not manifest_path:
        print("缺少 CP_HELDOUT_CASES / CP_HELDOUT_GOLD / CP_HELDOUT_MANIFEST", file=sys.stderr)
        return 2

    cases_root, gold_root = Path(cases), Path(gold)
    if not cases_root.is_dir() or not gold_root.is_dir():
        print("held-out 或判据目录不存在", file=sys.stderr)
        return 2

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    problems = validate_manifest(manifest, load_manifest_schema(REPO_ROOT / "contracts"))
    if problems:
        print("manifest 不符合 RunManifest：" + "; ".join(problems[:3]), file=sys.stderr)
        return 2

    mode = os.environ.get("CP_HELDOUT_TRANSPORT", "http")
    if mode == "dry":
        transport = DryTransport()
    else:
        base_url = os.environ.get("CP_HELDOUT_BASE_URL")
        if not base_url:
            print("http 模式需要 CP_HELDOUT_BASE_URL", file=sys.stderr)
            return 2
        transport = HttpTransport(base_url)

    runner = BenchmarkRunner(
        transport, cases_root=cases_root, gold_root=gold_root, contracts_root=REPO_ROOT / "contracts"
    )
    result = runner.run(manifest, repo_root=REPO_ROOT, repeats=1)
    summary = result["summary"]

    payload = {
        "leakFree": True,
        "caseCount": summary["caseCount"],
        "statusCounts": summary["statusCounts"],
        "groupMeans": summary["groupMeans"],
        "macroScore": summary["macroScore"],
        "costCoverage": summary["costCoverage"],
        "claimModes": summary["claimModes"],
        "heldOutScore": summary["macroScore"],
    }

    dumped = json.dumps(payload, ensure_ascii=False)
    leaked = [claim for claim in gold_claims(gold_root) if claim[:12] and claim[:12] in dumped]
    if leaked:
        payload["leakFree"] = False
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        print(f"输出里发现 {len(leaked)} 条判据原句，拒绝返回", file=sys.stderr)
        return 1

    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
