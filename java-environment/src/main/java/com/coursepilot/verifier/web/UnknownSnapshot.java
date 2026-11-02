package com.coursepilot.verifier.web;

/** curriculumSnapshotId 在库里不存在（契约 422，语义不合法）。 */
public class UnknownSnapshot extends RuntimeException {
    public UnknownSnapshot(String snapshotId) {
        super("培养快照不存在：" + snapshotId);
    }
}
