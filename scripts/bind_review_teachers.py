#!/usr/bin/env python3
"""把已导入的课程评价按教师显示名精确绑定到 teacherKey（工号）。

依据：2026-27 秋季官方开课表 sidecar 中 (courseCode, 教师姓名) -> 工号。
只绑定「同一课程 + 同一姓名 + 唯一工号」的评价；其余保持 teacherKey=null。
评价学期（termId）不改，历史教师不据此猜测绑定。

子命令（顺序执行）：
  plan    读取 A3 交付 JSON 与 sidecar，生成绑定计划与导入载荷（仅本地 data/private）
  export  通过 GET /api/v1/reviews/search 导出变更前的库内评价（备份）
  apply   校验导入载荷与库内备份一致后，POST /api/v1/reviews/import（按 reviewNoteId upsert）
  verify  按 teacherKey 检索，确认分教师结果出现

密钥只从 data/private/stack.env 读取，不打印。输出只含计数与定位 ID，不打印评价正文。
"""
import argparse
import collections
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DELIVERY = ROOT / "data/private/a3/review-import/delivery"
OFFERINGS = ROOT / "data/private/offerings"
OUT = ROOT / "data/private/review-binding"
ENV_FILE = ROOT / "data/private/stack.env"
BASE_URL = os.environ.get("CP_JAVA_BASE_URL_OVERRIDE", "http://127.0.0.1:8081")
SUBJECT_ID = "review-teacher-binding"
REVIEW_FILES = ["review-import-winter.json", "review-import-faculty-history.json"]
TRAILING_PUNCT = "，,。.．、;；:： "
PLAN_FILE = OUT / "binding-plan.json"
PAYLOAD_FILE = OUT / "import-payload.json"
BEFORE_FILE = OUT / "db-before-export.json"
AFTER_FILE = OUT / "db-after-export.json"
IMPORT_CHUNK = 200


def read_env(keys):
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() in keys:
            values[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in keys if not values.get(k)]
    if missing:
        sys.exit(f"stack.env 缺少配置项: {missing}")
    return values


def write_private_json(path, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clean_name(raw):
    """去掉空白与 OCR 残留的结尾标点（如 '赵尹，' -> '赵尹'）。"""
    return re.sub(r"\s+", "", raw or "").rstrip(TRAILING_PUNCT)


def load_delivery_notes():
    notes = {}
    for name in REVIEW_FILES:
        data = json.loads((DELIVERY / name).read_text(encoding="utf-8"))
        for note in data["notes"]:
            if note["reviewNoteId"] in notes:
                sys.exit(f"重复 reviewNoteId: {note['reviewNoteId']}")
            notes[note["reviewNoteId"]] = note
    return notes


def load_sidecar():
    with (DELIVERY / "teacher-display-sidecar.csv").open(encoding="utf-8-sig", newline="") as f:
        return {row["reviewNoteId"]: row for row in csv.DictReader(f)}


def load_timetable():
    """(courseCode, 教师姓名) -> 工号集合；工号来自官方开课 sidecar 的 teacherPairs（[工号, 姓名]）。"""
    rows = json.loads((OFFERINGS / "official-2026-27-fall-sidecar.json").read_text(encoding="utf-8"))
    ids = collections.defaultdict(set)
    course_names = {}
    offered = set()
    for r in rows:
        offered.add(r["courseCode"])
        course_names.setdefault(r["courseCode"], r["courseName"])
        for tid, name in r["teacherPairs"]:
            ids[(r["courseCode"], name)].add(tid)
    return ids, course_names, offered


def cmd_plan(_args):
    notes = load_delivery_notes()
    sidecar = load_sidecar()
    ids, course_names, offered = load_timetable()
    reasons = collections.Counter()
    bound_by_course = collections.defaultdict(collections.Counter)
    payload_notes = []
    plan_rows = []
    normalized = 0
    for rid, note in notes.items():
        row = sidecar.get(rid)
        if row is None or row["courseCode"] != note["courseCode"]:
            sys.exit(f"sidecar 三键不一致: {rid}")
        name = clean_name(row["teacherDisplayNameCandidate"])
        if name != row["teacherDisplayNameCandidate"].strip():
            normalized += 1
        matched = ids.get((note["courseCode"], name), set())
        if len(name) < 2:
            reason = "NAME_TOO_SHORT"
        elif note["courseCode"] not in offered:
            reason = "COURSE_NOT_OFFERED_THIS_TERM"
        elif not matched:
            reason = "NO_EXACT_NAME_IN_THIS_TERM_TIMETABLE"
        elif len(matched) > 1:
            reason = "AMBIGUOUS_TEACHER_ID"
        else:
            reason = "BOUND"
        reasons[reason] += 1
        historical = bool(row["historicalTeachingTermsCandidate"])
        plan_rows.append({"reviewNoteId": rid, "courseCode": note["courseCode"], "reason": reason,
                          "historicalTermsKnown": historical})
        if reason != "BOUND":
            continue
        teacher_key = next(iter(matched))
        bound_by_course[note["courseCode"]][(teacher_key, name)] += 1
        payload = dict(note)
        payload["teacherKey"] = teacher_key
        payload["termId"] = None
        payload["matchStatus"] = "COURSE_TEACHER_MATCHED"
        payload["teacherDisplayName"] = name
        payload_notes.append(payload)

    write_private_json(PAYLOAD_FILE, {"schemaVersion": "1.0", "notes": payload_notes})
    write_private_json(PLAN_FILE, {"rows": plan_rows, "reasonCounts": dict(reasons)})
    print(f"JSON 评价总数: {len(notes)}；sidecar 名字去除结尾标点: {normalized}")
    for k, v in reasons.most_common():
        print(f"  {k}: {v}")
    print(f"待绑定评价: {len(payload_notes)}，涉及课程: {len(bound_by_course)}")
    for code in sorted(bound_by_course, key=lambda c: -sum(bound_by_course[c].values())):
        top = ", ".join(f"{k[1]}({k[0]}) x{c}" for k, c in bound_by_course[code].most_common(5))
        print(f"  {code} {course_names.get(code, '-')}: {top}")
    print(f"导入载荷: {PAYLOAD_FILE}")


def api_get_all(path, params, env):
    """分页读取 /api/v1/reviews/search，返回全部 items。"""
    items, cursor = [], None
    while True:
        q = dict(params, limit=10)
        if cursor:
            q["cursor"] = cursor
        url = f"{BASE_URL}{path}?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(url, headers={
            "X-Request-Id": uuid.uuid4().hex, "X-Subject-Id": SUBJECT_ID,
            "X-Service-Key": env["CP_SERVICE_KEY"]})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        data = body["data"]
        items.extend(data["items"])
        cursor = data.get("nextCursor")
        if not cursor:
            return items


def course_codes_in_scope():
    return sorted({n["courseCode"] for n in load_delivery_notes().values()})


def export_db(env):
    result = {}
    for code in course_codes_in_scope():
        result[code] = api_get_all("/api/v1/reviews/search", {"courseCode": code}, env)
    return result


def cmd_export(_args):
    env = read_env(["CP_SERVICE_KEY"])
    snapshot = export_db(env)
    total = sum(len(v) for v in snapshot.values())
    write_private_json(BEFORE_FILE, snapshot)
    print(f"已导出变更前库内评价: {total} 条 -> {BEFORE_FILE}")


def cmd_apply(_args):
    env = read_env(["CP_SERVICE_KEY", "CP_ADMIN_KEY"])
    if not BEFORE_FILE.exists():
        sys.exit("缺少变更前备份，先运行 export")
    payload = json.loads(PAYLOAD_FILE.read_text(encoding="utf-8"))["notes"]
    before = json.loads(BEFORE_FILE.read_text(encoding="utf-8"))
    db_by_id = {item["reviewNoteId"]: item for codes in before.values() for item in codes}
    missing = [n["reviewNoteId"] for n in payload if n["reviewNoteId"] not in db_by_id]
    if missing:
        sys.exit(f"停止：{len(missing)} 条载荷在库内不存在，导入会新增而非更新: {missing[:5]}")
    mismatched = [n["reviewNoteId"] for n in payload
                  if db_by_id[n["reviewNoteId"]]["excerpt"] != n["excerpt"]
                  or db_by_id[n["reviewNoteId"]]["courseCode"] != n["courseCode"]]
    if mismatched:
        sys.exit(f"停止：{len(mismatched)} 条正文或课程与库内不一致: {mismatched[:5]}")
    imported = 0
    for start in range(0, len(payload), IMPORT_CHUNK):
        chunk = payload[start:start + IMPORT_CHUNK]
        body = json.dumps({"schemaVersion": "1.0", "notes": chunk}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{BASE_URL}/api/v1/reviews/import", data=body, method="POST", headers={
            "Content-Type": "application/json", "X-Request-Id": uuid.uuid4().hex,
            "X-Subject-Id": SUBJECT_ID, "X-Admin-Key": env["CP_ADMIN_KEY"],
            "X-Service-Key": env["CP_SERVICE_KEY"]})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            code = json.loads(err.read().decode("utf-8")).get("issues", [{}])[0].get("code")
            sys.exit(f"导入失败 HTTP {err.code} {code}")
        imported += result["data"]["importedCount"]
    print(f"导入请求已接收: {imported} 条（应等于 {len(payload)}）")
    after = export_db(env)
    write_private_json(AFTER_FILE, after)
    before_total = sum(len(v) for v in before.values())
    after_total = sum(len(v) for v in after.values())
    after_by_id = {item["reviewNoteId"]: item for codes in after.values() for item in codes}
    bad = [n["reviewNoteId"] for n in payload
           if after_by_id.get(n["reviewNoteId"], {}).get("teacherKey") != n["teacherKey"]]
    print(f"导入前总数 {before_total}，导入后总数 {after_total}（相等说明无重复）")
    print(f"绑定未生效的载荷: {len(bad)}")
    if after_total != before_total or bad:
        sys.exit("校验未通过，请用 export 备份回滚")


def cmd_verify(_args):
    env = read_env(["CP_SERVICE_KEY"])
    payload = json.loads(PAYLOAD_FILE.read_text(encoding="utf-8"))["notes"]
    by_course = collections.defaultdict(collections.Counter)
    for n in payload:
        by_course[n["courseCode"]][(n["teacherKey"], n["teacherDisplayName"])] += 1
    multi = [c for c, teachers in by_course.items() if len(teachers) >= 2]
    chosen = sorted(multi, key=lambda c: -sum(by_course[c].values()))[:3]
    for code in chosen:
        all_items = api_get_all("/api/v1/reviews/search", {"courseCode": code}, env)
        print(f"课程 {code}: 全部评价 {len(all_items)} 条")
        for (tkey, tname), _cnt in by_course[code].most_common():
            hits = api_get_all("/api/v1/reviews/search", {"courseCode": code, "teacherKey": tkey}, env)
            print(f"  {tname} ({tkey}): {len(hits)} 条")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in [("plan", cmd_plan), ("export", cmd_export), ("apply", cmd_apply), ("verify", cmd_verify)]:
        sub.add_parser(name).set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
