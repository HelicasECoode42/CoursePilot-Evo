package com.coursepilot.verifier.web;

/** The selected curriculum snapshot differs from the one bound to the academic record. */
public class SnapshotMismatch extends RuntimeException {
    private final String recordSnapshotId;
    private final String requestedSnapshotId;

    public SnapshotMismatch(String recordSnapshotId, String requestedSnapshotId) {
        super("学业记录绑定培养快照 " + recordSnapshotId + "，不能使用另一快照 "
            + requestedSnapshotId + " 进行核验");
        this.recordSnapshotId = recordSnapshotId;
        this.requestedSnapshotId = requestedSnapshotId;
    }

    public String getRecordSnapshotId() { return recordSnapshotId; }
    public String getRequestedSnapshotId() { return requestedSnapshotId; }
}
