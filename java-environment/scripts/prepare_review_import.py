#!/usr/bin/env python3
"""Join private teacher display names onto ReviewImport JSON by three source keys."""

import argparse
import csv
import json
from pathlib import Path

KEYS = ("reviewNoteId", "sourceRefId", "courseCode")


def prepare(reviews_path: Path, sidecar_path: Path, output_path: Path) -> int:
    payload = json.loads(reviews_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schemaVersion") != "1.0":
        raise ValueError("input must be a ReviewImport schemaVersion 1.0 object")
    notes = payload.get("notes")
    if not isinstance(notes, list) or not notes:
        raise ValueError("input notes must be a nonempty array")

    sidecar_by_id = {}
    with sidecar_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {*KEYS, "teacherDisplayNameCandidate"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("sidecar is missing required join or display-name columns")
        for row in reader:
            review_id = row["reviewNoteId"]
            if not review_id or review_id in sidecar_by_id:
                raise ValueError(f"sidecar has a missing or duplicate reviewNoteId: {review_id!r}")
            sidecar_by_id[review_id] = row

    seen = set()
    for note in notes:
        if not isinstance(note, dict):
            raise ValueError("each note must be an object")
        review_id = note.get("reviewNoteId")
        if review_id in seen:
            raise ValueError(f"duplicate reviewNoteId in JSON: {review_id}")
        seen.add(review_id)
        row = sidecar_by_id.get(review_id)
        if row is None or any(row[key] != str(note.get(key, "")) for key in KEYS):
            raise ValueError(f"sidecar triple-key mismatch for reviewNoteId: {review_id}")
        name = row["teacherDisplayNameCandidate"].strip()
        note["teacherDisplayName"] = name or None
        if note.get("teacherKey") is not None:
            raise ValueError(f"private display-name import requires null teacherKey: {review_id}")
        if note.get("matchStatus") == "COURSE_TEACHER_MATCHED":
            raise ValueError(f"display-name import cannot claim a teacher match: {review_id}")

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(notes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, required=True, help="ReviewImport JSON input")
    parser.add_argument("--sidecar", type=Path, required=True, help="teacher-display-sidecar.csv")
    parser.add_argument("--output", type=Path, required=True, help="local enriched JSON output")
    args = parser.parse_args()
    count = prepare(args.reviews, args.sidecar, args.output)
    print(f"Prepared {count} review records with display-only names.")


if __name__ == "__main__":
    main()
