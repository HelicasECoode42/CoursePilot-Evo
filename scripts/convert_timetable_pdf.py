#!/usr/bin/env python3
"""Convert the 2026-27 fall undergraduate timetable PDF into OfferingImport JSON batches.

Pipeline (local, private data only):
  1. PyMuPDF text extraction; each table row starts at a "2026-2027" cell.
  2. Field recovery for wrapped / shifted cells (glued capacity, teacher text in the
     class or credit cell, credit glued to the class label, etc.). Recovered rows are
     flagged in parse_flags, never silently trusted.
  3. Exact-duplicate removal; classId = <courseCode>-<nn> numbered in PDF order per
     course code (numbering is computed before any filter, so ids are stable).
  4. meetingTextRaw is the original time text (whitespace removed only). Java re-parses it.
     parseStatus is PARSED only for blocks the Java TimeParser grammar accepts.
  5. Output: OfferingImport batches (<= 2000 offerings each), a sidecar JSON with
     provenance and the teacher 工号 candidates, a manifest, and a stratified
     verification CSV.

Teacher 工号 is never written into teacherText. teacherKey stays null unless
--with-teacher-keys is given.

Run with the anaconda python (has PyMuPDF, openpyxl, jsonschema):
  /opt/anaconda3/bin/python3 scripts/convert_timetable_pdf.py --all
Validation only (no PDF needed), e.g. with the project venv:
  .venv/bin/python scripts/convert_timetable_pdf.py --validate-only
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import glob
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "data/raw/2026-11-school/附件3-26-27学年秋季学期本科生课程表.pdf"
DEFAULT_SCHEMA = ROOT / "contracts/schemas/domain.schema.json"
DEFAULT_OUT = ROOT / "data/private/offerings"
DEFAULT_CS_XLSX = ROOT / "data/raw/2024-computer-college-curricula.xlsx"
DEFAULT_CS_SHEET = "计科学直招"
DEFAULT_GE_PDF = ROOT / "data/raw/2026-11-school/上海大学通识教育课程培养方案.pdf"
DEFAULT_GE_DIR = ROOT / "data/raw/2026-11-school"

TERM_ID = "2026-2027-1"
MARKER = "2026-2027"
BATCH_SIZE = 2000
PART_PREFIX = "official-2026-27-fall-part"
CAMPUSES = ["宝山", "嘉定", "延长", "金山", "奉贤", "徐汇", "杨浦", "虹口", "松江"]
DAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
SECTION_CAP = 64
WEEK_CAP = 60
MEETING_CAP = 40

# One 上课时间 block, e.g. 星期一第1-2节{1-16周}. Whitespace must be removed first.
TIME_BLOCK = re.compile(r"(?:星期|周)([一二三四五六日天])第([\d,，\-]+)节\{([^{}]*)\}")
# Java TimeParser grammar (java-environment TimeParser.BLOCK): single range only.
JAVA_BLOCK = re.compile(r"(?:星期|周)([一二三四五六日天])第(\d+)(?:-(\d+))?节\{([^{}]*)\}")
JAVA_SEPARATORS = re.compile(r"[,，;；、/|]+")
# Teacher token: 8-digit 工号, optional "/name", optional capacity digits glued after it.
TEACHER_TOKEN = re.compile(r"(?<![\d/])(\d{8})(?:/([一-龥A-Za-z·\-]+))?(\d{0,3})(?!\d)")


# ---------------------------------------------------------------- time parsing

def parse_weeks(spec: str) -> list[int]:
    """Mirror of Java TimeParser.parseWeeks for the forms seen in the timetable."""
    parity = None
    m = re.search(r"[(（]([单双])[)）]\s*$", spec)
    if m:
        parity = m.group(1)
        spec = spec[: m.start()]
    weeks: set[int] = set()
    for part in re.split(r"[,，]", spec.replace("第", "").replace("周", "")):
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"\d+", part):
            weeks.add(int(part))
        elif re.fullmatch(r"\d+-\d+", part):
            a, b = (int(x) for x in part.split("-"))
            if a > b:
                raise ValueError("week range reversed")
            weeks.update(range(a, b + 1))
        else:
            raise ValueError(f"unknown week part {part!r}")
    if parity == "单":
        weeks = {w for w in weeks if w % 2 == 1}
    elif parity == "双":
        weeks = {w for w in weeks if w % 2 == 0}
    if not weeks or min(weeks) < 1 or max(weeks) > WEEK_CAP:
        raise ValueError("week set empty or out of contract range")
    return sorted(weeks)


def java_block_ok(block: str) -> bool:
    """True when the Java TimeParser grammar (single section range) accepts this block."""
    m = JAVA_BLOCK.fullmatch(block)
    if not m:
        return False
    start = int(m.group(2))
    end = int(m.group(3)) if m.group(3) else start
    if start > end or start < 1 or end > SECTION_CAP:
        return False
    try:
        parse_weeks(m.group(4))
    except ValueError:
        return False
    return True


def java_equivalent_parse(text: str) -> bool:
    """Reimplementation of TimeParser.parse acceptance (ok vs unknown), for stats only."""
    s = re.sub(r"\s+", "", text or "")
    if not s:
        return False
    blocks = 0
    residue = []
    cursor = 0
    for m in JAVA_BLOCK.finditer(s):
        residue.append(s[cursor:m.start()])
        cursor = m.end()
        if not java_block_ok(m.group(0)):
            return False
        blocks += 1
        if blocks > MEETING_CAP:
            return False
    residue.append(s[cursor:])
    if blocks == 0:
        return False
    return JAVA_SEPARATORS.sub("", "".join(residue)) == ""


def expand_meetings(time_text: str) -> tuple[str, list[dict]]:
    """Return (parseStatus, meetings). Multi-section blocks stay UNPARSED (Java cannot read them)."""
    if not time_text:
        return "UNPARSED", []
    meetings: list[dict] = []
    for block in time_text.split(";"):
        if not block:
            continue
        if not java_block_ok(block):
            return "UNPARSED", []
        m = JAVA_BLOCK.fullmatch(block)
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        meetings.append({
            "dayOfWeek": DAY_MAP[m.group(1)],
            "sectionStart": start,
            "sectionEnd": end,
            "weeks": parse_weeks(m.group(4)),
        })
    if not meetings or len(meetings) > MEETING_CAP:
        return "UNPARSED", []
    return "PARSED", meetings


# ---------------------------------------------------------------- PDF reading

def load_rows(pdf_path: Path) -> list[dict]:
    import fitz  # PyMuPDF; only needed for the full conversion

    doc = fitz.open(pdf_path)
    blocks: list[dict] = []
    cur = None
    for page_no, page in enumerate(doc, 1):
        for raw in page.get_text().split("\n"):
            s = raw.strip()
            if not s:
                continue
            if s == MARKER:
                if cur is not None:
                    blocks.append(cur)
                cur = {"page": page_no, "lines": [s]}
            elif cur is not None:
                cur["lines"].append(s)
    if cur is not None:
        blocks.append(cur)
    return blocks


def clean_course_name(cell: str) -> str:
    """Strip trailing credit and class label, undo doubled names produced by wrapped cells."""
    s = re.sub(r"\s+\d+(?:\.\d+)?$", "", cell.strip())
    s = re.sub(r"-\d{3,4}$", "", s).strip()
    for i in range(6, len(s) // 2 + 1):
        if s[:i] == s[i:2 * i]:
            s = s[:i]
            break
    return s


def analyse_teachers_and_capacity(text: str) -> dict:
    """text: all non-name cells joined with newlines (time blocks may still be present)."""
    s = re.sub(r"\s+", "", text)
    times = [m.group(0) for m in TIME_BLOCK.finditer(s)]
    masked = TIME_BLOCK.sub("\x01", s)
    for c in CAMPUSES:
        masked = masked.replace(c, "\x00" + c)
    tokens = list(TEACHER_TOKEN.finditer(masked))
    last_end = tokens[-1].end() if tokens else 0
    campus_pos = masked.find("\x00", last_end)
    campus = ""
    college = ""
    if campus_pos >= 0:
        for c in CAMPUSES:
            if masked.startswith("\x00" + c, campus_pos):
                campus = c
                break
        college = masked[campus_pos + 1 + len(campus):]
        between = masked[last_end:campus_pos]
    else:
        between = masked[last_end:]
    college = college.replace("\x01", "").replace("\x00", "").replace(";", "").strip()
    between_clean = between.replace("\x01", "").replace("\x00", "").replace(";", "")

    names = [t.group(2) for t in tokens if t.group(2)]
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    cap_candidates = [t.group(3) for t in tokens if t.group(3)]
    if between_clean and re.fullmatch(r"\d{1,3}", between_clean):
        cap_candidates.append(between_clean)
    return {
        "times": times,
        "teacher_ids": [t.group(1) for t in tokens],
        "teacher_pairs": [(t.group(1), t.group(2)) for t in tokens],
        "teacher_names": seen,
        "teacher_name_missing": any(t.group(2) is None for t in tokens),
        "capacity_raw": cap_candidates[0] if cap_candidates else "",
        "capacity_conflict": len(set(cap_candidates)) > 1,
        "residual": between_clean if between_clean and not re.fullmatch(r"\d{1,3}", between_clean) else "",
        "campus": campus,
        "college": college,
    }


def parse_row(block: dict, seq_in_file: int) -> dict:
    flags: list[str] = []
    cells = block["lines"][2:]
    if len(cells) < 4:
        return {"bad": True, "page": block["page"], "flags": ["short_record"]}
    code, name_cell, cls_cell, credit_cell = cells[0], cells[1], cells[2], cells[3]
    extra = cells[4:]
    credit = None
    cls_label = cls_cell

    if re.search(r"\d{8}/", cls_cell):
        # teacher text landed in the class cell: shift the rest of the row right
        flags.append("shift_fixed")
        extra = [cls_cell, credit_cell] + extra
        cls_label = ""
        credit_cell = ""
    else:
        m = re.fullmatch(r"(.*-\d{3,4})\s+(\d+(?:\.\d+)?)", cls_cell)
        if m:
            flags.append("credit_in_class_fixed")
            cls_label, credit = m.group(1), m.group(2)
            extra = [credit_cell] + extra
            credit_cell = ""

    if credit is None and re.fullmatch(r"\d+(?:\.\d+)?", credit_cell or ""):
        credit = credit_cell
    elif credit is None and credit_cell:
        flags.append("credit_cell_shifted")
        extra = [credit_cell] + extra
    if credit is None:
        m = re.search(r"\s(\d+(?:\.\d+)?)$", name_cell)
        if m:
            credit = m.group(1)
            flags.append("credit_from_name_cell")

    if not cls_label:
        # class label sometimes survives only inside the name cell, e.g. "...-0001 1.0"
        m = re.search(r"-\d{3,4}", name_cell)
        cls_label = re.sub(r"\s+\d+(?:\.\d+)?$", "", name_cell[m.start():]).strip() if m else ""

    course_name = clean_course_name(name_cell)
    if course_name != name_cell.strip() and re.search(r"-\d{3,4}", name_cell):
        flags.append("name_cell_cleaned")

    body = "\n".join(extra)
    info = analyse_teachers_and_capacity(body)
    # time text may also sit in the credit cell after a glued capacity
    m = re.match(r"^(\d{1,3})\s*(星期.*)$", credit_cell or "")
    if m:
        flags.append("capacity_glued_to_time_fixed")
        info["capacity_raw"] = info["capacity_raw"] or m.group(1)

    if not info["teacher_ids"]:
        flags.append("no_teacher_id")
    if info["teacher_name_missing"]:
        flags.append("teacher_name_missing")
    if not info["teacher_names"]:
        flags.append("teacher_text_placeholder")
    if info["capacity_conflict"]:
        flags.append("capacity_conflict")
    if info["residual"]:
        flags.append("residual_text")
    if not info["campus"]:
        flags.append("campus_missing")
    if not info["times"]:
        flags.append("no_time")
    if any(("," in t.split("节")[0]) or ("，" in t.split("节")[0]) for t in info["times"]):
        flags.append("multi_section_list")
    if credit is None:
        flags.append("credit_missing")
    if not re.fullmatch(r"[A-Za-z0-9]+", code):
        flags.append("code_bad")

    cap = None
    if info["capacity_raw"]:
        cap = int(info["capacity_raw"])
        if cap > 100000:
            cap = None
            flags.append("capacity_out_of_range")

    # 教师 display text: names only. 工号 goes to sidecar only.
    teacher_text = "、".join(info["teacher_names"]) if info["teacher_names"] else "待确认"

    meeting_text = ";".join(info["times"])
    frag = info["residual"]
    if frag and re.search(r"星期|周|第|节|\{", frag):
        # A time block was cut by the PDF cell break (e.g. "星期五第5-"). Keep the fragment in
        # meetingTextRaw so Java sees residue and returns UNKNOWN instead of a silently shorter timetable.
        flags.append("time_fragment_truncated")
        meeting_text = ";".join(info["times"] + [frag])
    return {
        "bad": False,
        "page": block["page"],
        "seq_in_file": seq_in_file,
        "courseCode": code,
        "courseName": course_name,
        "classLabel": cls_label,
        "teacherIds": info["teacher_ids"],
        "teacherPairs": info["teacher_pairs"],
        "teacherNames": info["teacher_names"],
        "teacherText": teacher_text,
        "credits": float(credit) if credit is not None else None,
        "capacity": cap,
        "capacityRaw": info["capacity_raw"],
        "meetingTextRaw": meeting_text,
        "campus": info["campus"],
        "college": info["college"],
        "flags": flags,
        "rawCells": cells,
    }


# ---------------------------------------------------------------- curriculum / 通识 coverage

def expand_cs_codes(cell: str) -> tuple[list[str], bool]:
    """Expand 课程编号 cells. Returns (concrete codes, has_unresolved_pattern)."""
    cell = (cell or "").strip()
    if not cell or cell == "*":
        return [], False
    m = re.fullmatch(r"([0-9A-Za-z]{5,})~(\d+)", cell)
    if m:
        start, tail = m.group(1), m.group(2)
        if not start.isdigit() or len(tail) > len(start):
            return [start], True
        prefix = start[: len(start) - len(tail)]
        end = int(prefix + tail)
        s_int = int(start)
        if end < s_int or end - s_int > 50:
            return [start], True
        width = len(start)
        return [str(i).zfill(width) for i in range(s_int, end + 1)], False
    if re.search(r"[xX]", cell):
        return [], True
    if re.fullmatch(r"[0-9A-Za-z]{5,}", cell):
        return [cell], False
    return [], True


def cs_curriculum_codes(xlsx: Path, sheet: str) -> tuple[list[str], dict]:
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        raise SystemExit(f"sheet {sheet!r} not in {xlsx}")
    codes: list[str] = []
    names: dict[str, str] = {}
    unresolved = 0
    for row in wb[sheet].iter_rows(values_only=True):
        if len(row) < 9 or row[8] != "课程明细":
            continue
        cs, unres = expand_cs_codes(str(row[2] or ""))
        unresolved += unres
        for c in cs:
            codes.append(c)
            names.setdefault(c, str(row[1]))
    unique = list(dict.fromkeys(codes))
    return unique, {"detail_rows_codes": len(unique), "unresolved_pattern_cells": unresolved, "names": names}


def general_ed_coverage(offering_codes: set[str], ge_pdf: Path, ge_dir: Path) -> dict:
    import fitz
    import openpyxl

    out: dict = {}
    doc = fitz.open(ge_pdf)
    text = "\n".join(p.get_text() for p in doc)
    appendix_codes = sorted(set(re.findall(r"(?<![0-9A-Za-z])([A-Z]{0,4}\d{6,10}[A-Z0-9]{0,4})(?![0-9A-Za-z])", text)))
    out["通识方案PDF"] = {
        "codes": len(appendix_codes),
        "in_fall_timetable": sum(1 for c in appendix_codes if c in offering_codes),
    }
    all_codes: set[str] = set()
    for xlsx in sorted(glob.glob(str(ge_dir / "*类课程清单.xlsx"))):
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
        codes: list[str] = []
        idx = None
        for row in wb.worksheets[0].iter_rows(values_only=True):
            cells = [str(x).strip() if x is not None else "" for x in row]
            if idx is None:
                if "课程号" in cells:
                    idx = cells.index("课程号")
                continue
            if idx < len(cells) and cells[idx]:
                codes.append(cells[idx])
        name = Path(xlsx).stem
        out[name] = {"codes": len(codes), "in_fall_timetable": sum(1 for c in codes if c in offering_codes)}
        all_codes.update(codes)
    out["4清单合计"] = {"codes": len(all_codes), "in_fall_timetable": sum(1 for c in all_codes if c in offering_codes)}
    return out


# ---------------------------------------------------------------- build

def build(args: argparse.Namespace) -> dict:
    pdf = Path(args.pdf)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    blocks = load_rows(pdf)
    rows = [parse_row(b, i) for i, b in enumerate(blocks)]
    bad = [r for r in rows if r["bad"]]
    rows = [r for r in rows if not r["bad"]]

    # exact duplicate removal (same content, not just same label)
    dedupe_key = lambda r: (r["courseCode"], tuple(r["teacherIds"]), r["classLabel"], r["meetingTextRaw"],
                            r["capacity"], r["credits"], r["campus"], r["college"])
    seen: dict = {}
    kept: list[dict] = []
    exact_dups: list[dict] = []
    for r in rows:
        k = dedupe_key(r)
        if k in seen:
            exact_dups.append({"page": r["page"], "courseCode": r["courseCode"], "classLabel": r["classLabel"]})
            continue
        seen[k] = True
        kept.append(r)

    # label collisions: same (code, class label) but different content are kept with distinct nn
    label_counter = Counter((r["courseCode"], r["classLabel"]) for r in kept)
    label_collisions = sorted({f"{c}|{l}" for (c, l), n in label_counter.items() if n > 1})

    # classId numbering per course code, PDF order
    per_code: Counter = Counter()
    for r in kept:
        per_code[r["courseCode"]] += 1
        r["classId"] = f"{r['courseCode']}-{per_code[r['courseCode']]:02d}"
        r["sourceRefId"] = f"official:2026-27-fall:p{r['page']:03d}:r{r['seq_in_file']:04d}"

    all_codes = {r["courseCode"] for r in kept}
    course_names = {r["courseCode"]: r["courseName"] for r in kept}

    # selection
    selected = kept
    selection_mode = "all"
    if not args.all:
        if not args.college and not args.course_codes_from_curriculum:
            raise SystemExit("pass --all, --college or --course-codes-from-curriculum")
        selection_mode = "filtered"
        cs_codes: set[str] = set()
        if args.course_codes_from_curriculum:
            cs_codes, _ = cs_curriculum_codes(Path(args.course_codes_from_curriculum), args.cs_sheet)
            cs_codes = set(cs_codes)
        selected = [
            r for r in kept
            if (args.college and any(c in r["college"] for c in args.college))
            or (r["courseCode"] in cs_codes)
        ]

    # teacher keys (opt-in only)
    def teacher_key(r: dict):
        if args.with_teacher_keys and r["teacherIds"]:
            return r["teacherIds"][0]
        return None

    # meetings
    status_counter: Counter = Counter()
    offerings: list[dict] = []
    sidecar: list[dict] = []
    for r in selected:
        status, meetings = expand_meetings(r["meetingTextRaw"])
        if r["meetingTextRaw"] == "":
            status = "UNPARSED"
        status_counter[status] += 1
        offerings.append({
            "courseCode": r["courseCode"],
            "classId": r["classId"],
            "teacherKey": teacher_key(r),
            "teacherText": r["teacherText"],
            "credits": r["credits"],
            "capacity": r["capacity"],
            "meetingTextRaw": r["meetingTextRaw"],
            "meetings": meetings,
            "parseStatus": status,
            "sourceRefId": r["sourceRefId"],
        })
        sidecar.append({
            "classId": r["classId"],
            "courseCode": r["courseCode"],
            "courseName": r["courseName"],
            "classLabel": r["classLabel"],
            "teacherNames": r["teacherNames"],
            "teacherPairs": [[i, n] for i, n in r["teacherPairs"]],
            "teacherIdCandidates": r["teacherIds"],
            "capacityRaw": r["capacityRaw"],
            "campus": r["campus"],
            "college": r["college"],
            "page": r["page"],
            "sourceRefId": r["sourceRefId"],
            "meetingTextRaw": r["meetingTextRaw"],
            "parseStatus": status,
            "javaParseable": bool(r["meetingTextRaw"]) and java_equivalent_parse(r["meetingTextRaw"]),
            "parseFlags": r["flags"],
        })

    # batches
    for old in glob.glob(str(out_dir / f"{PART_PREFIX}*.json")):
        Path(old).unlink()
    parts = []
    total_parts = max(1, (len(offerings) + BATCH_SIZE - 1) // BATCH_SIZE)
    captured = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).replace(microsecond=0).isoformat()
    max_week = max((m["weeks"][-1] for o in offerings for m in o["meetings"]), default=16)
    max_section = max((m["sectionEnd"] for o in offerings for m in o["meetings"]), default=12)
    calendar = {"weeks": max(16, max_week), "sectionsPerDay": max(12, max_section)}
    for i in range(total_parts):
        chunk = offerings[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
        if not chunk:
            break
        payload = {
            "schemaVersion": "1.0",
            "termId": TERM_ID,
            "sourceKind": args.source_kind,
            "capturedAt": captured,
            "calendar": calendar,
            "offerings": chunk,
        }
        path = out_dir / f"{PART_PREFIX}{i + 1}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        parts.append({"file": path.name, "offerings": len(chunk)})

    (out_dir / "official-2026-27-fall-sidecar.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # verification sample: stratified by page bins, one random row per bin
    rng = random.Random(args.seed)
    max_page = max(r["page"] for r in kept)
    bins = 50
    sample_rows: list[dict] = []
    for b in range(bins):
        lo = 1 + b * max_page // bins
        hi = (b + 1) * max_page // bins
        pool = [r for r in kept if lo <= r["page"] <= hi]
        if pool:
            sample_rows.append(rng.choice(pool))
    with (out_dir / "verification-sample.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sample_no", "pdf_page", "classId", "学年", "学期", "课程代码", "课程", "教学班名称",
                    "学分", "教师(姓名)", "教师工号候选", "容量", "上课时间(原文)", "校区", "开课学院",
                    "parse_flags"])
        for n, r in enumerate(sample_rows, 1):
            w.writerow([n, r["page"], r["classId"], "2026-2027", "秋", r["courseCode"], r["courseName"],
                        r["classLabel"], "" if r["credits"] is None else r["credits"],
                        "、".join(r["teacherNames"]), ";".join(r["teacherIds"]),
                        "" if r["capacity"] is None else r["capacity"], r["meetingTextRaw"], r["campus"],
                        r["college"], ";".join(r["flags"])])

    # coverage
    offer_codes = all_codes
    cs_stats = {}
    if Path(args.cs_xlsx).exists():
        cs_codes, meta = cs_curriculum_codes(Path(args.cs_xlsx), args.cs_sheet)
        found = [c for c in cs_codes if c in offer_codes]
        missing = [c for c in cs_codes if c not in offer_codes]
        cs_stats = {
            "concrete_codes": len(cs_codes),
            "found_in_fall_timetable": len(found),
            "unresolved_pattern_cells": meta["unresolved_pattern_cells"],
            "missing_examples": [f"{c} {meta['names'].get(c, '')}" for c in missing[:12]],
        }
    ge_stats = {}
    if Path(args.ge_pdf).exists():
        ge_stats = general_ed_coverage(offer_codes, Path(args.ge_pdf), Path(args.ge_dir))

    java_ok = sum(1 for s in sidecar if s["javaParseable"])
    flag_counter: Counter = Counter()
    for r in kept:
        for f in r["flags"]:
            flag_counter[f] += 1

    manifest = {
        "source": {"file": pdf.name, "sha256": raw_sha, "pages": max_page},
        "termId": TERM_ID,
        "sourceKind": args.source_kind,
        "capturedAt": captured,
        "calendar": calendar,
        "selection": selection_mode,
        "rowsExtracted": len(blocks),
        "rowsBad": len(bad),
        "exactDuplicatesRemoved": exact_dups,
        "labelCollisionsKeptWithDistinctIds": label_collisions,
        "offeringsAllUnique": len(kept),
        "offeringsOutput": len(offerings),
        "parseStatus": dict(status_counter),
        "javaParseableOutput": java_ok,
        "parseFlagCounts": dict(flag_counter),
        "parts": parts,
        "csCurriculumCoverage": cs_stats,
        "generalEdCoverage": ge_stats,
        "validation": {},
    }
    (out_dir / "official-2026-27-fall-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


# ---------------------------------------------------------------- validation

def validate(out_dir: Path, schema_path: Path, source_kind: str) -> dict:
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    enum_path = schema["$defs"]["OfferingImport"]["properties"]["sourceKind"]["enum"]
    patched = copy.deepcopy(schema)
    patched_enum = patched["$defs"]["OfferingImport"]["properties"]["sourceKind"]["enum"]
    if source_kind not in patched_enum:
        patched_enum.append(source_kind)

    def make(defs_root: dict):
        root = {"$schema": schema["$schema"], "$defs": defs_root["$defs"], "$ref": "#/$defs/OfferingImport"}
        return jsonschema.Draft202012Validator(root, format_checker=jsonschema.FormatChecker())

    strict = make(schema)
    temp = make(patched)
    result: dict = {"sourceKindEnumInContract": enum_path, "patchedEnumForValidation": patched_enum, "files": {}}
    for path in sorted(glob.glob(str(out_dir / f"{PART_PREFIX}*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        errs_strict = [e.message for e in strict.iter_errors(data)]
        errs_patched = [e.message for e in temp.iter_errors(data)]
        result["files"][Path(path).name] = {
            "offerings": len(data["offerings"]),
            "errors_against_unpatched_contract": len(errs_strict),
            "errors_with_temp_enum_patch": len(errs_patched),
            "first_error_with_patch": errs_patched[:3],
        }
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", default=str(DEFAULT_PDF))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    ap.add_argument("--source-kind", default="OFFICIAL_DOCUMENT",
                    help="OfferingImport.sourceKind; OFFICIAL_DOCUMENT is not in the contract enum yet")
    ap.add_argument("--all", action="store_true", help="export every offering row")
    ap.add_argument("--college", action="append", default=[],
                    help="export rows whose 开课学院 contains this text (repeatable)")
    ap.add_argument("--course-codes-from-curriculum", default="",
                    help="xlsx path; export rows whose courseCode is in the curriculum sheet (--cs-sheet)")
    ap.add_argument("--cs-sheet", default=DEFAULT_CS_SHEET)
    ap.add_argument("--cs-xlsx", default=str(DEFAULT_CS_XLSX))
    ap.add_argument("--ge-pdf", default=str(DEFAULT_GE_PDF))
    ap.add_argument("--ge-dir", default=str(DEFAULT_GE_DIR))
    ap.add_argument("--with-teacher-keys", action="store_true",
                    help="also set teacherKey to the first 工号 (default: null, 工号 kept in sidecar)")
    ap.add_argument("--seed", type=int, default=20261102)
    ap.add_argument("--validate-only", action="store_true", help="only validate existing part files")
    args = ap.parse_args()

    if args.validate_only:
        res = validate(Path(args.out_dir), Path(args.schema), args.source_kind)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    manifest = build(args)
    manifest["validation"] = validate(Path(args.out_dir), Path(args.schema), args.source_kind)
    (Path(args.out_dir) / "official-2026-27-fall-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: manifest[k] for k in (
        "rowsExtracted", "rowsBad", "exactDuplicatesRemoved", "labelCollisionsKeptWithDistinctIds",
        "offeringsAllUnique", "offeringsOutput", "parseStatus", "javaParseableOutput", "parts",
        "csCurriculumCoverage", "generalEdCoverage")}
    summary["parseFlagCounts"] = manifest["parseFlagCounts"]
    summary["validation"] = manifest["validation"]
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main())
