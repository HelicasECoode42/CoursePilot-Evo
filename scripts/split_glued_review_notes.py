#!/usr/bin/env python3
"""拆分粘连在一条里的课程评价，并清理 PDF/OCR 残留，然后替换库内旧评价。

问题：计机学院评价 PDF 的多条评价用分隔符「Ⅱ」（另有少量「丨」「』」「‖」「||」）连在同一条 ReviewNote 里，
界面显示成一大段，且所有段都挂在同一个课程/教师下。

子命令：
  plan   读取 A3 交付 JSON（冬季刊 + 计机学院）与 sidecar、已绑定教师的导入载荷，生成拆分计划与导入载荷
         （只写 data/private/review-binding，不联网）。
  apply  通过 HTTP 替换库内评价：先导出备份，DELETE 旧粘连 ID（管理员接口），再 POST 新载荷（按 reviewNoteId upsert）。
         需要 Java 服务已运行且已包含 DELETE /api/v1/reviews/import。

规则（不改变事实，只改切分与显示名）：
- 分隔符处切开，去掉分隔符旁独立的 OCR 残留及首尾空白，保留「口头」「接口」等正文。
- 只删除两侧都是中日文字符之间的空格（PDF 换行造成的「游泳 健将」「讲 台」）；英文和数字之间的空格保留。
- 段长不足 2 个字符的碎片丢弃（计数输出）。
- 新 ID = 原 reviewNoteId + "-s01"、"-s02"…；sourceRefId 同样加后缀；dimensions 沿用原条目（来源标签是整块的）。
- 教师：teacherDisplayName 取 sidecar 的 teacherDisplayNameCandidate（清去结尾标点）；teacherKey 只沿用
  bind_review_teachers.py 已按「同课程 + 同名 + 唯一工号」验证过的绑定，绝不新增绑定。
  绑定的段升为 COURSE_TEACHER_MATCHED，未绑定的保持原 matchStatus。
- 没有分隔符的评价保留原 ID，只做空格/残留清理并补上 teacherDisplayName，便于显示「未标明老师」以外的姓名。

密钥只从 data/private/stack.env 读取，不打印。输出只含计数与定位 ID，不打印评价正文。
"""
import argparse
import collections
import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bind_review_teachers as b  # noqa: E402  复用读取交付包、sidecar 与库内导出的函数

OUT = b.OUT
PLAN_FILE = OUT / "split-plan.json"
PAYLOAD_FILE = OUT / "split-import-payload.json"
RETIRE_FILE = OUT / "split-retire-ids.json"
BEFORE_FILE = OUT / "split-db-before.json"
AFTER_FILE = OUT / "split-db-after.json"
BOUND_PAYLOAD = OUT / "import-payload.json"
CHUNK = 200

SEPARATORS = ["Ⅱ", "‖", "||", "｜｜", "丨", "』"]
SEP_RE = re.compile("|".join(re.escape(s) for s in SEPARATORS))
EDGE_ARTIFACTS = "丨｜|」「『』 \t　"
CJK = r"　-鿿＀-￯"
CJK_GAP = re.compile(rf"(?<=[{CJK}])\s+(?=[{CJK}])")
MIN_SEGMENT = 2


def clean_text(text):
    """去掉 PDF 换行造成的中日文字之间的空格，并去掉首尾空白。"""
    return CJK_GAP.sub("", text).strip()


def clean_piece(piece, after_separator=False, before_separator=False):
    s = piece.strip(EDGE_ARTIFACTS)
    if after_separator:
        s = re.sub(r"^[IⅠ口](?:\s+|$)", "", s)
    if before_separator:
        s = re.sub(r"(?:^|\s+)口$", "", s)
    s = s.strip(EDGE_ARTIFACTS)
    return clean_text(s)


def split_excerpt(excerpt):
    """返回 (片段列表, 是否含分隔符)。片段已清理且长度达标。"""
    pieces = SEP_RE.split(excerpt)
    if len(pieces) == 1:
        cleaned = clean_piece(excerpt)
        return ([cleaned] if cleaned else []), False
    out = []
    for i, p in enumerate(pieces):
        c = clean_piece(p, after_separator=i > 0, before_separator=i < len(pieces) - 1)
        if len(c) >= MIN_SEGMENT:
            out.append(c)
    return out, True


def load_bound_keys():
    if not BOUND_PAYLOAD.exists():
        sys.exit("缺少绑定载荷，请先运行 bind_review_teachers.py plan")
    rows = json.loads(BOUND_PAYLOAD.read_text(encoding="utf-8"))["notes"]
    return {n["reviewNoteId"]: n["teacherKey"] for n in rows}


def build(notes, sidecar, bound):
    out_notes, retire = [], []
    stats = collections.Counter()
    for rid in sorted(notes):
        note = notes[rid]
        row = sidecar.get(rid)
        if row is None or row["courseCode"] != note["courseCode"]:
            sys.exit(f"sidecar 三键不一致: {rid}")
        name = b.clean_name(row["teacherDisplayNameCandidate"]) or None
        tkey = bound.get(rid)
        segments, split = split_excerpt(note["excerpt"])
        stats["notes_total"] += 1
        if not segments:
            stats["notes_dropped_empty"] += 1
            retire.append(rid)
            continue
        if split:
            stats["notes_glued"] += 1
            stats["segments_dropped_short"] += len(SEP_RE.split(note["excerpt"])) - len(segments)
            retire.append(rid)
            ids = [f"{rid}-s{i:02d}" for i in range(1, len(segments) + 1)]
            stats["segments_created"] += len(segments)
        else:
            stats["notes_kept_id"] += 1
            ids = [rid]
        for new_id, text in zip(ids, segments):
            suffix = new_id[len(rid):]
            status = "COURSE_TEACHER_MATCHED" if tkey else note["matchStatus"]
            out_notes.append({
                "reviewNoteId": new_id,
                "courseCode": note["courseCode"],
                "teacherKey": tkey,
                "termId": note.get("termId"),
                "sourceKind": note["sourceKind"],
                "publishedAt": note.get("publishedAt"),
                "sourceUrl": note.get("sourceUrl"),
                "excerpt": text,
                "dimensions": note.get("dimensions", []),
                "matchStatus": status,
                "sourceRefId": note["sourceRefId"] + suffix,
                "teacherDisplayName": name,
            })
            stats["notes_out"] += 1
            if tkey:
                stats["notes_teacher_bound"] += 1
            if name:
                stats["notes_with_teacher_name"] += 1
    return out_notes, sorted(set(retire)), stats


def cmd_plan(_args):
    notes = b.load_delivery_notes()
    sidecar = b.load_sidecar()
    bound = load_bound_keys()
    out_notes, retire, stats = build(notes, sidecar, bound)
    ids = [n["reviewNoteId"] for n in out_notes]
    if len(ids) != len(set(ids)):
        sys.exit("拆分后出现重复 reviewNoteId")
    for n in out_notes:
        if len(n["sourceRefId"]) > 120 or len(n["reviewNoteId"]) > 120 or len(n["excerpt"]) > 1500:
            sys.exit(f"字段超限: {n['reviewNoteId']}")
    b.write_private_json(PAYLOAD_FILE, {"schemaVersion": "1.0", "notes": out_notes})
    b.write_private_json(RETIRE_FILE, {"reviewNoteIds": retire})
    b.write_private_json(PLAN_FILE, {"counts": dict(stats), "retireCount": len(retire)})
    print(json.dumps({"counts": dict(stats), "retireCount": len(retire)}, ensure_ascii=False, indent=2))
    print(f"载荷: {PAYLOAD_FILE}\n退役 ID: {RETIRE_FILE}")


def request(method, path, payload, env):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"X-Request-Id": uuid.uuid4().hex, "X-Subject-Id": b.SUBJECT_ID, "X-Service-Key": env["CP_SERVICE_KEY"]}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if method != "GET":
        headers["X-Admin-Key"] = env["CP_ADMIN_KEY"]
    req = urllib.request.Request(f"{b.BASE_URL}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))["data"]
    except urllib.error.HTTPError as err:
        code = (json.loads(err.read().decode("utf-8")).get("issues") or [{}])[0].get("code")
        sys.exit(f"{method} {path} 失败 HTTP {err.code} {code}")


def export_courses(codes, env):
    result = {}
    for code in sorted(codes):
        result[code] = b.api_get_all("/api/v1/reviews/search", {"courseCode": code}, env)
    return result


def cmd_apply(_args):
    env = b.read_env(["CP_SERVICE_KEY", "CP_ADMIN_KEY"])
    payload = json.loads(PAYLOAD_FILE.read_text(encoding="utf-8"))["notes"]
    retire = json.loads(RETIRE_FILE.read_text(encoding="utf-8"))["reviewNoteIds"]
    codes = {n["courseCode"] for n in payload}
    # A retired source note may have no surviving fragment, so its course can
    # be absent from the new payload. Include those courses in the backup and
    # post-import export set as well.
    source_notes = b.load_delivery_notes()
    codes.update(source_notes[r]["courseCode"] for r in retire)
    before = export_courses(codes, env)
    b.write_private_json(BEFORE_FILE, before)
    before_ids = {i["reviewNoteId"] for items in before.values() for i in items}
    retire_present = [r for r in retire if r in before_ids]
    new_ids = [n["reviewNoteId"] for n in payload if n["reviewNoteId"] not in before_ids]
    print(f"导出备份: 库内 {len(before_ids)} 条；退役旧 ID 库内存在 {len(retire_present)} / {len(retire)}；新增 ID {len(new_ids)}")

    deleted = 0
    for i in range(0, len(retire), CHUNK):
        deleted += request("DELETE", "/api/v1/reviews/import",
                           {"schemaVersion": "1.0", "reviewNoteIds": retire[i:i + CHUNK]}, env)["deletedCount"]
    print(f"已删除旧粘连评价: {deleted} 条")

    imported = 0
    for i in range(0, len(payload), CHUNK):
        chunk = payload[i:i + CHUNK]
        imported += request("POST", "/api/v1/reviews/import",
                            {"schemaVersion": "1.0", "notes": chunk}, env)["importedCount"]
    print(f"已导入新评价载荷: {imported} 条（应等于 {len(payload)}）")

    after = export_courses(codes, env)
    b.write_private_json(AFTER_FILE, after)
    after_items = {i["reviewNoteId"]: i for items in after.values() for i in items}
    still = [r for r in retire if r in after_items]
    wrong_teacher = [n["reviewNoteId"] for n in payload
                     if after_items.get(n["reviewNoteId"], {}).get("teacherKey") != n["teacherKey"]]
    print(f"导入后库内 {len(after_items)} 条（导入前 {len(before_ids)}）；残留旧 ID {len(still)}；绑定不一致 {len(wrong_teacher)}")
    if still or wrong_teacher:
        sys.exit("校验未通过，请用 split-db-before.json 备份回滚")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("plan", cmd_plan), ("apply", cmd_apply)]:
        sub.add_parser(name).set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
