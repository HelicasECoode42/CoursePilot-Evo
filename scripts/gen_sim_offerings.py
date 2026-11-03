#!/usr/bin/env python3
"""生成「计算机科学与技术（直招）」的模拟开课快照（OfferingImport，sourceKind=SYNTHETIC）。

输入（只读，都在 data/ 下，已被 .gitignore 覆盖）：
  - data/raw/2024-computer-college-curricula.xlsx 的「计科学直招」页签（培养方案明细）
  - data/private/a3/review-import/delivery/teacher-display-sidecar.csv（有评价的教师展示名，按课程号）
  - data/private/offerings/shu-tongshi-seminar-offering-import.json（同学提供的研讨课班次，可选合并）

输出（只写到私有目录，绝不提交）：
  - data/private/offerings/cs-sim-offerings.json

规则要点：
  - 课程：「课程明细」行，排除「实践教学环节」（军训、实习、毕设、实训、大型作业、思政实践等，
    都不是固定时段的课堂班次）。组要求行（通识课课程组等）不是单门课程，也排除。
  - 课程号区间（如 01014125~127）按区间展开为多门课（与培养方案快照一致）；编号含 "xx" 的
    （体育、大学英语）原表编号规则未定，与培养方案快照一样保留原样，同号下多个班次。
  - 每门课 2–3 个班次（classId = <课程号>-SIM<序号>），每周次数 = min(4, ceil(学分/2))，
    每次 2 节，节次取 1-2/3-4/5-6/7-8/9-10/11-12；星期一到星期五随机分布，全部由固定种子决定。
  - 同一建议学期的课优先用「主班次」排开互不冲突（保证存在可行方案）；其余班次和约 12%
    的主班次随机放置，因此会有冲突。
  - 教师：有评价数据的课程用评价里的教师展示名（不含 stable key，teacherKey 为 null）；
    没有的用「某老师（模拟）」。
  - meetingTextRaw 与 TimeParser 格式一致，例如 周一第1-2节{第1-16周},周三第1-2节{第1-16周}。

用法：
  python3 scripts/gen_sim_offerings.py            # 生成并校验（需要 openpyxl、jsonschema）
  python3 scripts/gen_sim_offerings.py --no-teammate   # 只输出模拟班次，不合并同学文件
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRICULUM_XLSX = ROOT / "data/raw/2024-computer-college-curricula.xlsx"
CURRICULUM_SHEET = "计科学直招"
SIDECAR = ROOT / "data/private/a3/review-import/delivery/teacher-display-sidecar.csv"
TEAMMATE = ROOT / "data/private/offerings/shu-tongshi-seminar-offering-import.json"
OUTPUT = ROOT / "data/private/offerings/cs-sim-offerings.json"
SCHEMA = ROOT / "contracts/schemas/domain.schema.json"

SEED = 20261102
TERM_ID = "synthetic-2026"  # 与同学文件一致，两者合并为一个快照
CAPTURED_AT = "2026-11-02T14:05:00+08:00"
WEEKS = 16
SECTIONS_PER_DAY = 13
DAYS = [1, 2, 3, 4, 5]  # 周一至周五
SLOTS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)]
DAY_NAMES = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五"}
FICTIONAL_SURNAMES = [
    "张",
    "李",
    "王",
    "刘",
    "陈",
    "杨",
    "赵",
    "黄",
    "周",
    "吴",
    "徐",
    "孙",
    "马",
    "胡",
]
EXCLUDED_CATEGORY = "实践教学环节"
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


def expand_code(raw: str) -> list[str]:
    """课程号展开：01014125~127 -> [01014125, 01014126, 01014127]；无区间则原样返回。"""
    raw = raw.strip()
    if "~" not in raw:
        return [raw]
    start, end = (x.strip() for x in raw.split("~", 1))
    if not end.isdigit() or not start:
        return [start]
    prefix = start[: len(start) - len(end)]
    first = int(start[len(start) - len(end) :])
    last = int(end)
    return [f"{prefix}{str(v).zfill(len(end))}" for v in range(first, last + 1)]


def parse_term(text: str | None) -> str:
    """建议学期文本 -> 分组键（同组的课优先排开）。"""
    if not text:
        return "unscheduled"
    m = re.search(r"第(\d+)学期", text)
    if m:
        return f"term{int(m.group(1))}"
    if "夏季" in text:
        return "summer"
    return "multi"


def load_curriculum() -> tuple[list[dict], list[dict]]:
    import openpyxl

    wb = openpyxl.load_workbook(CURRICULUM_XLSX, read_only=True)
    ws = wb[CURRICULUM_SHEET]
    courses, excluded = [], []
    for row in ws.iter_rows(values_only=True):
        if not row or row[0] != "计科学直招" or row[8] != "课程明细":
            continue
        name, code_raw, category, credits_raw, term_text = (
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
        )
        if category == EXCLUDED_CATEGORY:
            excluded.append(
                {
                    "name": name,
                    "category": category,
                    "reason": "实践教学环节，非固定时段班次",
                }
            )
            continue
        if not code_raw:
            excluded.append(
                {"name": name, "category": category, "reason": "无课程号（组要求行）"}
            )
            continue
        credits = float(credits_raw) if credits_raw not in (None, "") else 1.0
        # 区间课号（如 01014125~127）按区间展开为多门课，与培养方案快照的展开方式一致；
        # 学分按课程数均分（取 0.5 的整数倍，最后一门取余数）。
        members = expand_code(str(code_raw))
        n = len(members)
        base_share = math.floor(credits / n * 2) / 2 if n > 1 else credits
        for idx, code in enumerate(members):
            share = (
                base_share if idx < n - 1 else round(credits - base_share * (n - 1), 2)
            )
            courses.append(
                {
                    "name": name,
                    "rawCode": str(code_raw),
                    "courseCode": code,
                    "category": category,
                    "credits": share,
                    "term": parse_term(term_text),
                    "placeholderCode": "xx" in str(code_raw),
                }
            )
    return courses, excluded


def load_teachers() -> dict[str, list[str]]:
    pools: dict[str, Counter] = defaultdict(Counter)
    with SIDECAR.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            name = (r.get("teacherDisplayNameCandidate") or "").strip()
            code = (r.get("courseCode") or "").strip()
            if name and code:
                pools[code][name] += 1
    return {code: [n for n, _ in c.most_common()] for code, c in pools.items()}


def meeting_text(meetings: list[tuple[int, int, list[int]]]) -> str:
    parts = []
    for day, slot, weeks in meetings:
        start, end = SLOTS[slot]
        w = weeks_text(weeks)
        parts.append(f"{DAY_NAMES[day]}第{start}-{end}节{{{w}}}")
    return ",".join(parts)


def weeks_text(weeks: list[int]) -> str:
    return f"第{weeks[0]}-{weeks[-1]}周"


def build_sections(
    courses: list[dict], teachers: dict[str, list[str]], rng: random.Random
):
    offerings: list[dict] = []
    summary = Counter()
    # 同一课程号下的班次序号（合并行、占位编号共用一个号时保证 classId 唯一）
    class_seq: Counter = Counter()
    fictional_used: dict[str, set] = defaultdict(set)

    # 按建议学期分组，同组课程的主班次互相避让
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in courses:
        groups[c["term"]].append(c)
    occupied: dict[str, set] = defaultdict(set)  # 每组已占用的 (day, slot)

    def pick_config(
        sessions: int, avoid: set | None, group_occ: set | None
    ) -> list[tuple[int, int]]:
        for _ in range(300):
            days = sorted(rng.sample(DAYS, sessions))
            slots = [rng.randrange(len(SLOTS)) for _ in days]
            cfg = list(zip(days, slots))
            if group_occ is not None and any(x in group_occ for x in cfg):
                continue
            if avoid is not None and set(cfg) == avoid:
                continue
            return cfg
        # 找不到不冲突的组合：返回随机组合（会与同组课冲突，属于有意保留的冲突）
        days = sorted(rng.sample(DAYS, sessions))
        return [(d, rng.randrange(len(SLOTS))) for d in days]

    for term in sorted(groups, key=lambda t: (t.startswith("term") is False, t)):
        for c in groups[term]:
            code = c["courseCode"]
            sessions = min(4, max(1, math.ceil(c["credits"] / 2)))
            n_sections = rng.choice([2, 3])
            pool = list(teachers.get(code, []))
            rng.shuffle(pool)
            prior_cfgs: list[set] = []
            for i in range(n_sections):
                # 周次：单次课的 1 学分或 2 学分课程，部分只在前 8 周或后 8 周
                if sessions == 1 and c["credits"] <= 2 and rng.random() < 0.5:
                    weeks = (
                        list(range(1, 9)) if rng.random() < 0.5 else list(range(9, 17))
                    )
                else:
                    weeks = list(range(1, WEEKS + 1))
                primary = i == 0
                if primary and rng.random() >= 0.12:
                    cfg = pick_config(sessions, None, occupied[term])
                else:
                    cfg = pick_config(
                        sessions, set(prior_cfgs[0]) if prior_cfgs else None, None
                    )
                    if prior_cfgs:
                        # 与已有班次的时间尽量不同
                        for _ in range(50):
                            if all(set(cfg) != p for p in prior_cfgs):
                                break
                            cfg = pick_config(sessions, None, None)
                if primary:
                    occupied[term].update(cfg)
                prior_cfgs.append(set(cfg))

                class_seq[code] += 1
                seq = class_seq[code]
                class_id = f"{code}-SIM{seq:02d}"
                if pool:
                    teacher = pool[i % len(pool)]
                else:
                    while True:
                        teacher = f"{rng.choice(FICTIONAL_SURNAMES)}老师（模拟）"
                        if (
                            teacher not in fictional_used[code]
                            or len(fictional_used[code]) >= 14
                        ):
                            break
                    fictional_used[code].add(teacher)
                meetings = [(d, s, weeks) for d, s in cfg]
                meetings.sort(key=lambda m: (m[0], m[1]))
                offerings.append(
                    {
                        "courseCode": code,
                        "classId": class_id,
                        "teacherKey": None,
                        "teacherText": teacher,
                        "credits": c["credits"],
                        "capacity": None,
                        "meetingTextRaw": meeting_text(meetings),
                        "meetings": [
                            {
                                "dayOfWeek": d,
                                "sectionStart": SLOTS[s][0],
                                "sectionEnd": SLOTS[s][1],
                                "weeks": list(weeks),
                            }
                            for d, s, weeks in meetings
                        ],
                        "parseStatus": "PARSED",
                        "sourceRefId": f"sim:{code}:{seq}",
                    }
                )
                summary["sections"] += 1
            summary["courses"] += 1
    return offerings, summary


def validate(payload: dict) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    domain = json.loads(SCHEMA.read_text(encoding="utf-8"))
    root = {"$ref": "#/$defs/OfferingImport", "$defs": domain["$defs"]}
    errors = sorted(
        Draft202012Validator(root, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda e: list(e.path),
    )
    if errors:
        for e in errors[:10]:
            print("schema error:", list(e.path), e.message, file=sys.stderr)
        raise SystemExit(f"契约校验失败，共 {len(errors)} 处")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--no-teammate", action="store_true", help="不合并同学的研讨课班次文件"
    )
    args = ap.parse_args()

    rng = random.Random(SEED)
    courses, excluded = load_curriculum()
    teachers = load_teachers()
    offerings, summary = build_sections(courses, teachers, rng)

    teammate_count = 0
    if not args.no_teammate and TEAMMATE.exists():
        # 合并：同学的文件已是 SYNTHETIC、同一 termId，班次号（-S1）与模拟班次号（-SIM）不冲突
        src = json.loads(TEAMMATE.read_text(encoding="utf-8"))
        assert src["termId"] == TERM_ID and src["calendar"] == {
            "weeks": WEEKS,
            "sectionsPerDay": SECTIONS_PER_DAY,
        }
        offerings = src["offerings"] + offerings
        teammate_count = len(src["offerings"])

    classes = [o["classId"] for o in offerings]
    dup = [k for k, v in Counter(classes).items() if v > 1]
    if dup:
        raise SystemExit(f"班次编号重复：{dup[:5]}")
    for o in offerings:
        assert TOKEN.match(o["classId"]) and TOKEN.match(o["courseCode"]), o["classId"]

    payload = {
        "schemaVersion": "1.0",
        "termId": TERM_ID,
        "sourceKind": "SYNTHETIC",
        "capturedAt": CAPTURED_AT,
        "calendar": {"weeks": WEEKS, "sectionsPerDay": SECTIONS_PER_DAY},
        "offerings": offerings,
    }
    validate(payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    real_teacher = sum(
        1
        for o in offerings
        if "-SIM" in o["classId"] and not o["teacherText"].endswith("（模拟）")
    )
    print(f"模拟课程 {summary['courses']} 门，模拟班次 {summary['sections']} 个")
    print(f"合并同学研讨课班次 {teammate_count} 个；合计 {len(offerings)} 个")
    print(f"使用评价教师展示名的模拟班次 {real_teacher} 个")
    print("排除（课程明细中的非课堂项）:")
    for e in excluded:
        print(f"  - {e['name']}（{e['category']}）：{e['reason']}")
    print(f"已写入 {OUTPUT}（私有目录，不提交）")


if __name__ == "__main__":
    main()
