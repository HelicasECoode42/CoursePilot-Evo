# School progress import proposal

This proposal adds a versioned school progress snapshot without changing the
existing `AcademicRecord` contract. The importer preserves the source category
tree (`nodeId`, `parentId`, school node id, leaf flag), course rows, capture
time, and source label. Category names are not keys: parent and child nodes may
have identical names and distinct requirements.

## Data flow

1. The browser adapter reads the currently displayed school page and returns
   the snapshot to the already-open CoursePilot tab.
2. The Records page submits the snapshot to the Python session gateway with an
   `Idempotency-Key`.
3. Python validates the bounded schema and forwards it through the fixed Java
   tool allowlist with the authenticated session subject.
4. Java persists the source snapshot and updates the session's academic record
   from the imported course rows in one transaction. Java remains the owner of
   credit audits and candidate requirements.

## Proposed endpoints

- `PUT /api/v1/school-progress` on Python, bearer session auth,
  `Idempotency-Key`, body containing schema version and snapshot.
- `PUT /api/v1/school-progress` on Java, authenticated service headers and
  `Idempotency-Key`; subject is derived from trusted `X-Subject-Id`.
- `GET /api/v1/school-progress` on Python returns the latest saved snapshot for
  that subject.

The successful response data contains `receipt` (`schoolProgressId`,
`contentHash`, `importedAt`, `reused`), the full persisted `snapshot`, and the
updated `academicRecord`. The same subject, key, and normalized body replays the saved response. Reusing
the key with different content returns 409. A successful response is emitted
only after Java commits both the source snapshot and the academic record.

## Course outcomes

Only an explicit, recognized status marker maps to `PASSED`, `FAILED`,
`IN_PROGRESS`, or `NOT_TAKEN`. Unrecognized status is `UNKNOWN`; missing grades
do not determine course outcome. `NOT_TAKEN` rows remain in the source snapshot
but are omitted from the completed-course audit input. `IN_PROGRESS` is retained
as an academic record fact and does not count as completed credit.

## Failure behavior

Malformed or oversized snapshots return 422/413. Reused idempotency keys with
different normalized content return 409. If persistence fails, neither the
source snapshot nor the corresponding academic record is reported as imported.
The browser bridge reports success only after the Python response confirms the
Java transaction has committed.
