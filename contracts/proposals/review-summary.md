# Recommendation review basis proposal

## Purpose

Expose the evidence available for each recommended course so the client can show
course facts and review coverage without deriving a score from a small number of
records.

## Proposed fields

Add these fields to each `Recommendation.courseRationales[]` item:

| Field | Type | Producer | Meaning |
| --- | --- | --- | --- |
| `courseSourceRefIds` | `string[]`, maximum 20 | Python Runner | Source references returned by Java for that course in the selected curriculum snapshot. The model does not author this field. |
| `reviewBasisStatus` | `HAS_EVIDENCE \| NO_RECORDS \| NOT_QUERIED \| null` | Python Runner | `HAS_EVIDENCE` means at least one queried review record exists for the course; `NO_RECORDS` means the course was queried and the returned list was empty; `NOT_QUERIED` means no review query was made for the course. `null` means an older response did not record the query state. |
| `rationaleSource` | `MODEL \| COURSE_FACTS \| null` | Python Runner | `MODEL` marks a reason authored by the configured model; `COURSE_FACTS` marks the factual course-catalog description used when a model reason is absent; `null` means an older response has no source label. |
| `reviewEvidenceRefs` | `{reviewNoteId, sourceRefId}[]`, maximum 10 | Python Runner | Source reference for each cited review record. Both IDs are derived from Java facts and are paired so the client can trace a citation even when it has not loaded the review excerpt. |

`reviewNoteIds` continues to identify the particular review records cited in the
model's course rationale. Each cited record resolves to its `sourceRefId` in the
retrieved Java evidence. The Runner validates that cited review IDs belong to the
same course and were returned by Java.

## Client behavior

- Show `暂无评价依据` for `NO_RECORDS`.
- Show `未查询评价` for `NOT_QUERIED`.
- Show `评价依据状态未记录` for `null`.
- For `HAS_EVIDENCE`, show cited review excerpts and their source references.
- When cited excerpts are not loaded, show the cited review IDs with their paired
  source references. If the course has records but this rationale cited none, say
  that course reviews exist but were not cited by this rationale.
- Show `courseSourceRefIds` with the course reason so catalog claims remain
  traceable.
- Do not turn record counts, dimension tags, or review text into a numeric rating.

## Compatibility and implementation

The four proposed fields are output-only and server-derived. They do not add model
tokens or require a model response change. The Python answer schema exposes them;
the contracts owner updates `contracts/schemas/domain.schema.json` and both
OpenAPI response definitions before integration.
