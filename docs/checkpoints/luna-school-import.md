# School progress import checkpoint

## Scope and data flow

The school-page adapter reads the visible category tree, course rows, and
status-marker signatures. It sends a normalized, allow-listed snapshot to the
already-open CoursePilot tab. The Records page sends the snapshot to the
Python session API with an idempotency key. Python validates the request and
forwards it to the fixed Java tool. Java persists the source snapshot and its
updated `AcademicRecord` in one transaction. The web store publishes import
success only after that response arrives.

The source category tree remains available as a school report. Java continues
to own curriculum audits and candidate requirements. School category names
are not keys, so parent and child nodes with identical names remain separate.
Only explicitly mapped status icons produce `PASSED`, `FAILED`, `IN_PROGRESS`,
or `NOT_TAKEN`; missing or conflicting mappings remain `UNKNOWN`. Unknown
outcomes are not counted as completed courses or credits.

## Technology and failure handling

- Browser adapter: JavaScript content script, page DOM extraction, extension
  service-worker request lock, and a localhost CoursePilot bridge.
- Web: Vue and TypeScript, school progress domain normalization, session store,
  Records view, and Credit Plan school-report reference.
- Python: FastAPI/Pydantic session API and fixed Java tool allowlist.
- Java: Spring Boot, JPA snapshot repository, transactional service, and
  `Idempotency-Key` replay handling.

The bridge rejects unsupported source pages and concurrent imports. It returns
success only after Java persistence succeeds; validation, auth, transport, and
conflicting idempotency failures return a failed import result. Repeating the
same key and body replays the response. A new capture time with unchanged
curriculum and source content reuses the natural snapshot; a different
curriculum produces a separate content hash. A missing latest snapshot returns
404. The adapter does not infer course outcome from grade text.

## Verification

- Java `SchoolProgressEndpointTest`: passed with JDK 25 and the configured
  Mockito javaagent.
- Web typecheck and scoped Vitest: passed, 73 tests across five files.
- Python formatting and lint for the school-progress tool client, route, and
  tool-client tests: passed.
- Root-agent live integration: HTTP import returned 200; same-key replay
  matched; GET returned 200; changing only `capturedAt` reused the persisted
  snapshot.
- Python full suite: 193 passed, 2 failed in schema-example tests because the
  concurrent planning contract added two examples whose definitions were not
  present in the test's `SCHEMA_DEFS` mapping. The school-progress scoped
  tests are tracked separately from this contract synchronization issue.

## Remaining verification

The source-page legend mapping is covered by a fictional DOM fixture. Root
must complete live validation of the expanded extension preview and each
school icon signature on the actual page. No real personal school data is
stored in fixtures. The current planner remains in its configured mode when
school progress is imported; imported in-progress rows do not establish next
term offerings or verified schedule times.

## Credit plan interaction follow-up

The credit selection page now reads both `interestTags` and the existing
`careerText` from the planning store. Chinese word segmentation supplies terms
to the existing candidate relevance score, so free-form development direction
text affects candidate order. Candidates remain manually selectable when the
Java audit gap is unknown; the ledger keeps the gap unknown and no completion
combinations are generated. Common audit UNKNOWN messages use the same
student-facing explanation in Records and Credit Plan. The ready page labels a
record from its `sourceKind`, so a `USER_IMPORT` record remains labeled as a
user import during simulation.

Verification: Web typecheck and ESLint passed; CreditPlan, Records, and
Question page tests passed (35 tests).

## Authorized curriculum import follow-up

The current file database contains a published 95-course curriculum snapshot
whose importer receipt is for track `cs-direct` and whose workbook hash matches
the local A1 workbook. Its existing record is `SYNTHETIC/SYNTHETIC`; the 95
course facts must enter through a new import to retain their source meaning.
The local Java import endpoint accepts `sourceKind=CURRICULUM_FILE` and
publishes a separate `CURRICULUM_FILE/UNVERIFIED` snapshot with `CURRICULUM`
membership provenance. It does not promote source validation to VERIFIED or
change the existing synthetic snapshot. The same working database contains 258
`USER_IMPORT` reviews (152 `COURSE_ONLY`, 106 `UNVERIFIED`) and 5 synthetic
reviews.

The endpoint documentation now distinguishes the default synthetic fixture
path from the explicit curriculum-file path. The in-memory endpoint test
verifies source metadata on list/query, snapshot separation, and idempotent
reuse. No import was run against the file database.
