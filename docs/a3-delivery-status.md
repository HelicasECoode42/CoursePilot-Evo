# A3 delivery status: A-F3, A-F4, A-F5

Status as of 2026-10-26: **partial; evaluation coverage and several data rules remain under review.** This note records the safe, shareable deliverables. It does not publish school PDFs, raw OCR, course-level review text, teacher names, the original curriculum workbook, or complete historical offering data. Those materials remain in the ignored local `data/private/a3/` directory.

## A-F3: academic-record input

The current `AcademicRecordInput` contract can represent complete and incomplete transcripts, passed/failed/in-progress/unknown outcomes, and nullable credits/terms. Synthetic positive and negative examples are included in the contract example index. Two attempts for the same course can be represented as separate rows, but the contract has no attempt number or repeat-grade selection rule. That policy still needs confirmation with B before the example can define production behavior.

## A-F4: teacher reviews

The private working set contains schema-valid ReviewImport records and separate source maps. Public examples include only a fictional ReviewImport record. The source material is incomplete and does not support a complete review catalog:

- Across 667 A1 course-path rows, current winter-issue TOC comparison has 52 exact course-section matches, 56 title variants that need manual review, and 559 rows with no title match in the processed table of contents. These are matching states, not proof that every course in a matched section has a publishable review, nor proof that unmatched courses have no reviews.
- The private winter working set has 142 schema-valid review notes and four additional long teacher-section records that exceed the ReviewImport `excerpt` limit. Six more teacher headings were not recognized by OCR. These records remain local for manual review.
- The faculty booklet's teacher-only comments have only limited, unverified course candidates from a static SHUOSC history crosswalk. Unmatched comments are not assigned to guessed courses.
- A1-path-by-path course coverage and all real teacher names/reviews remain in local private files. The owner is manually auditing the missing coverage and investigating ways to resolve it.

Do not use candidate or OCR-only associations as verified teacher/course/term facts. The shared `ReviewImport` contract was not changed for this work.

## A-F5: offerings and time examples

Four public fixtures use only synthetic data: two different class IDs under one course code, a time conflict, a no-conflict pair, and an unknown-time case. Expected outcomes are: preserve the two distinct class IDs; detect overlapping meetings; detect no conflict for non-overlapping meetings; and keep unknown time as `UNPARSED`, without deciding that it is conflict-free. These are expected outcomes for B to verify, not evidence that Java's unique TimeParser has produced those results.

The local audit of the published historical source found that it does not provide the project's required `classId` field. Historical source rows were not relabeled as current browser snapshots or synthetic records, and no complete historical dataset is published here. A real historical import still needs a source-type/mapping decision with B/C and validation by B's TimeParser.

## Public synthetic examples

The ten A3 fixtures are listed in [`contracts/examples/index.json`](../contracts/examples/index.json) and checked against the current shared schemas by `scripts/check_contracts.py`. Their `SYNTHETIC` values are illustrative only.

## Local-only review materials

The detailed course coverage, merged review rows, teacher sidecars, unmatched records, OCR outputs, and source PDFs stay under ignored `data/private/a3/`. They are not included in this branch. The coverage work is ongoing; the absence of a public review record must not be interpreted as evidence that no student evaluation exists.
