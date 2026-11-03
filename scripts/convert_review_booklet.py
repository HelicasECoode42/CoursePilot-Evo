#!/usr/bin/env python3
"""Convert the 学盟社 选课小本本 2025-2026 秋季刊 PDF into ReviewImport JSON.

Each individual review (a line starting with a term prefix such as "22-秋：") becomes one
ReviewNote. Course headings ("2.1 程序设计(C 语言)") are mapped to a 2026-27 fall course code
by exact normalized name, only when the name is unique in the timetable. Teacher headings
("2.1.1 高洪皓") are bound to a 工号 only when (courseCode, teacher name) appears in the
timetable with exactly one 工号. Unmapped reviews are not imported (courseCode is required by
the contract) and are counted in the stats file.

Source: sourceKind USER_IMPORT (student-made booklet). Validation status for the booklet is
UNVERIFIED, so matchStatus defaults to UNVERIFIED for every note (see --teacher-match-status).

Run with the anaconda python (PyMuPDF + jsonschema):
  /opt/anaconda3/bin/python3 scripts/convert_review_booklet.py
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = ROOT / "data/raw/2026-11-school/学盟社：选课小本本 2025-2026学年秋季刊.pdf"
DEFAULT_SIDECAR = ROOT / "data/private/offerings/official-2026-27-fall-sidecar.json"
DEFAULT_SCHEMA = ROOT / "contracts/schemas/domain.schema.json"
DEFAULT_OUT = ROOT / "data/private/reviews"

BOOKLET_TAG = "xkxbb-2025-08-16"
BOOKLET_DATE = "2025-08-16"
EXCERPT_CAP = 1500
NOTES_PER_FILE = 200  # ReviewController limit (maxItems 200)
TERM_PREFIX = re.compile(r"^(\d{2})-(秋|春|冬|夏)：(.*)$")
HEADING = re.compile(r"^(\d+(?:\.\d+)+)\s+(\S.*?)\s*$")
CHAPTER_ONLY = re.compile(r"^第\d+\s?章\s*$")
TAGS = {"推荐", "吐槽"}
WATERMARK_CHARS = set("选课小本出品")
WATERMARK_PHRASES = ["选课小本本出品", "课小本本出品", "选课小本本", "小本本出品", "本本出品", "选课小本出品"]
TEACHER_CHAR_LIMIT = 8
HEADING_BAD = set("，。！？；,.!?;")


# ---------------------------------------------------------------- normalization

def norm(text: str) -> str:
    t = text.replace("（", "(").replace("）", ")").replace("　", " ")
    t = re.sub(r"\s+", "", t)
    return t


def term_id_for(year2: str, season: str) -> str | None:
    y = int(year2)
    if season == "秋":
        return f"20{y:02d}-20{y + 1:02d}-1"
    if season == "春":
        return f"20{y - 1:02d}-20{y:02d}-2"
    return None  # 冬/夏 are short terms with no mapping in the contract


# ---------------------------------------------------------------- PDF text

def booklet_lines(pdf: Path) -> tuple[list[dict], dict]:
    import fitz

    doc = fitz.open(pdf)
    stats = {"pages": len(doc), "watermark_lines_dropped": 0, "inline_watermarks_removed": 0,
             "lone_number_lines_dropped": 0}
    out: list[dict] = []
    body_started = False
    for pno, page in enumerate(doc, 1):
        raw = [ln.rstrip() for ln in page.get_text().split("\n")]
        lines = []
        for ln in raw:
            s = ln.strip()
            if not s:
                continue
            if re.sub(r"\s+", "", s) and set(re.sub(r"\s+", "", s)) <= WATERMARK_CHARS | {"品"}:
                stats["watermark_lines_dropped"] += 1
                continue
            cleaned = s
            for ph in WATERMARK_PHRASES:
                if ph in cleaned:
                    stats["inline_watermarks_removed"] += cleaned.count(ph)
                    cleaned = cleaned.replace(ph, "")
            cleaned = cleaned.strip()
            if not cleaned:
                continue
            lines.append(cleaned)
        # page-number footers: lone integers at the very start or end of a page
        for idx in (0, -1):
            if lines and re.fullmatch(r"\d{1,3}", lines[idx]):
                lines.pop(idx)
                stats["lone_number_lines_dropped"] += 1
        for s in lines:
            if not body_started:
                if CHAPTER_ONLY.match(s):
                    body_started = True
                continue
            out.append({"page": pno, "text": s})
    return out, stats


def classify_events(lines: list[dict]) -> list[dict]:
    events = []
    for item in lines:
        s = item["text"]
        m_term = TERM_PREFIX.match(s)
        m_head = HEADING.match(s)
        if s in TAGS:
            events.append({"kind": "tag", "text": s, "page": item["page"]})
        elif m_term:
            events.append({"kind": "review", "year": m_term.group(1), "season": m_term.group(2),
                           "text": m_term.group(3), "page": item["page"]})
        elif m_head and not m_head.group(2)[0].isdigit() and len(m_head.group(2)) <= 40 \
                and not (set(m_head.group(2)) & HEADING_BAD):
            events.append({"kind": "head", "num": m_head.group(1), "name": m_head.group(2),
                           "page": item["page"]})
        else:
            events.append({"kind": "text", "text": s, "page": item["page"]})
    return events


def structure(events: list[dict]) -> list[dict]:
    """Attach each review to its (course, teacher) heading. Heading level is inferred from numbering
    plus whether the heading is a container (its next significant event is a child heading)."""
    course = None  # dict(num, name, page)
    teacher = None
    reviews: list[dict] = []
    current = None
    n = len(events)
    for i, ev in enumerate(events):
        if ev["kind"] == "head":
            # a container heading is followed directly by its child heading
            nxt = events[i + 1] if i + 1 < n else None
            is_container = nxt is not None and nxt["kind"] == "head" and nxt["num"].startswith(ev["num"] + ".")
            if is_container:
                course = {"num": ev["num"], "name": ev["name"], "page": ev["page"]}
                teacher = None
                current = None
                continue
            if course and ev["num"].startswith(course["num"] + ".") and \
                    ev["num"].count(".") == course["num"].count(".") + 1:
                teacher = {"num": ev["num"], "name": ev["name"], "page": ev["page"]}
                current = None
                continue
            # leaf course heading with no teacher subsections
            course = {"num": ev["num"], "name": ev["name"], "page": ev["page"]}
            teacher = None
            current = None
            continue
        if ev["kind"] == "tag":
            current = None
            continue
        if ev["kind"] == "review":
            if course is None or teacher is None:
                current = None
                continue
            current = {"course": course, "teacher": teacher, "page": ev["page"], "year": ev["year"],
                       "season": ev["season"], "parts": [ev["text"]], "tag": None}
            reviews.append(current)
            continue
        # plain text: continuation of the open review, else ignore (intro, ads, etc.)
        if current is not None:
            current["parts"].append(ev["text"])
    return reviews


def join_parts(parts: list[str]) -> str:
    out = ""
    for p in parts:
        if out and out[-1].isascii() and out[-1].isalnum() and p[:1].isascii() and p[:1].isalnum():
            out += " "
        out += p
    return re.sub(r"[ \t]+", " ", out).strip()


# ---------------------------------------------------------------- timetable mapping

def load_timetable_index(sidecar: Path) -> tuple[dict, dict, dict]:
    rows = json.loads(sidecar.read_text(encoding="utf-8"))
    name_to_codes: dict[str, set[str]] = defaultdict(set)
    pair_to_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    code_names: dict[str, str] = {}
    for r in rows:
        code = r["courseCode"]
        name = r["courseName"]
        if name:
            name_to_codes[norm(name)].add(code)
            code_names.setdefault(code, name)
        for tid, tname in r.get("teacherPairs", []):
            if tname:
                pair_to_ids[(code, norm(tname))].add(tid)
    return name_to_codes, pair_to_ids, code_names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", default=str(DEFAULT_PDF))
    ap.add_argument("--timetable-sidecar", default=str(DEFAULT_SIDECAR))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    ap.add_argument("--teacher-match-status", default="UNVERIFIED",
                    choices=["UNVERIFIED", "COURSE_TEACHER_MATCHED"],
                    help="matchStatus for notes with a teacher binding (booklet validation is UNVERIFIED)")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines, text_stats = booklet_lines(pdf)
    events = classify_events(lines)
    reviews = structure(events)
    name_to_codes, pair_to_ids, _ = load_timetable_index(Path(args.timetable_sidecar))

    stats: Counter = Counter()
    notes: list[dict] = []
    sidecar_rows: list[dict] = []
    unmapped_courses: Counter = Counter()
    seen_ids: set[str] = set()
    for seq, rv in enumerate(reviews, 1):
        stats["reviews_total"] += 1
        course_name = rv["course"]["name"]
        teacher_name = rv["teacher"]["name"]
        codes = name_to_codes.get(norm(course_name), set())
        if len(codes) != 1:
            stats["course_unmapped" if not codes else "course_ambiguous"] += 1
            unmapped_courses[course_name] += 1
            continue
        code = next(iter(codes))
        stats["course_mapped"] += 1

        ids = pair_to_ids.get((code, norm(teacher_name)), set())
        teacher_key = next(iter(ids)) if len(ids) == 1 else None
        if teacher_key:
            stats["teacher_bound"] += 1
        elif len(ids) > 1:
            stats["teacher_ambiguous_unbound"] += 1
        else:
            stats["teacher_not_in_timetable"] += 1

        excerpt = join_parts(rv["parts"])
        if not excerpt:
            stats["empty_excerpt_skipped"] += 1
            continue
        if len(excerpt) > EXCERPT_CAP:
            stats["excerpt_truncated"] += 1
            excerpt = excerpt[:EXCERPT_CAP]

        term = term_id_for(rv["year"], rv["season"])
        if term is None:
            stats["term_unmapped_" + rv["season"]] += 1
        note_id = f"review:{BOOKLET_TAG}:{seq:05d}"
        if note_id in seen_ids:
            raise SystemExit(f"duplicate reviewNoteId {note_id}")
        seen_ids.add(note_id)
        match = args.teacher_match_status if teacher_key else "UNVERIFIED"
        notes.append({
            "reviewNoteId": note_id,
            "courseCode": code,
            "teacherKey": teacher_key,
            "termId": term,
            "sourceKind": "USER_IMPORT",
            "publishedAt": None,
            "sourceUrl": None,
            "excerpt": excerpt,
            "dimensions": [],
            "matchStatus": match,
            "sourceRefId": f"{BOOKLET_TAG}:p{rv['page']:03d}:r{seq:05d}",
            "teacherDisplayName": teacher_name,
        })
        sidecar_rows.append({
            "reviewNoteId": note_id,
            "courseCode": code,
            "courseName": course_name,
            "teacherName": teacher_name,
            "teacherKey": teacher_key or "",
            "termPrefix": f"{rv['year']}-{rv['season']}",
            "booklet": BOOKLET_TAG,
            "bookletDate": BOOKLET_DATE,
            "page": rv["page"],
            "excerptChars": len(excerpt),
        })

    stats["notes_imported"] = len(notes)
    stats["reviews_not_imported"] = stats["reviews_total"] - len(notes)

    # output: one file when it fits the 200-note limit, otherwise numbered parts
    for old in list(out_dir.glob("fall-booklet-import*.json")):
        old.unlink()
    part_files = []
    chunks = [notes[i:i + NOTES_PER_FILE] for i in range(0, len(notes), NOTES_PER_FILE)] or [[]]
    for i, chunk in enumerate(chunks, 1):
        name = "fall-booklet-import.json" if len(chunks) == 1 else f"fall-booklet-import-part{i}.json"
        payload = {"schemaVersion": "1.0", "notes": chunk}
        (out_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        part_files.append({"file": name, "notes": len(chunk)})

    with (out_dir / "fall-booklet-sidecar.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sidecar_rows[0].keys()) if sidecar_rows else ["reviewNoteId"])
        w.writeheader()
        w.writerows(sidecar_rows)

    # validation against ReviewImport (USER_IMPORT is already in the contract enum)
    import jsonschema
    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    root = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/ReviewImport"}
    validator = jsonschema.Draft202012Validator(root, format_checker=jsonschema.FormatChecker())
    validation = {}
    for pf in part_files:
        data = json.loads((out_dir / pf["file"]).read_text(encoding="utf-8"))
        errs = [e.message for e in validator.iter_errors(data)]
        validation[pf["file"]] = {"notes": len(data["notes"]), "errors": len(errs), "first": errs[:3]}

    # sanity: Java controller forbids teacherKey-less COURSE_TEACHER_MATCHED and checks unique ids
    java_rule_violations = sum(1 for n in notes if n["matchStatus"] == "COURSE_TEACHER_MATCHED" and not n["teacherKey"])

    fresh = {
        "source": {"file": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                   "bookletDate": BOOKLET_DATE, "tag": BOOKLET_TAG, "validationStatus": "UNVERIFIED"},
        "sourceKind": "USER_IMPORT",
        "textExtraction": text_stats,
        "reviewCounts": dict(stats),
        "matchStatusCounts": dict(Counter(n["matchStatus"] for n in notes)),
        "termIdCounts": dict(Counter(str(n["termId"]) for n in notes)),
        "parts": part_files,
        "validation": validation,
        "javaRuleViolations": java_rule_violations,
        "topUnmappedCourseNames": unmapped_courses.most_common(25),
        "generatedAt": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).replace(microsecond=0).isoformat(),
    }
    (out_dir / "fall-booklet-stats.json").write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")
    print(json.dumps(fresh, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
