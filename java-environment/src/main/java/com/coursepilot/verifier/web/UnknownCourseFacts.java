package com.coursepilot.verifier.web;

/** A snapshot membership exists, but its own course facts or provenance are incomplete. */
public class UnknownCourseFacts extends RuntimeException {
    private final String snapshotId;
    private final String courseCode;

    public UnknownCourseFacts(String snapshotId, String courseCode) {
        super("培养快照 " + snapshotId + " 中课程 " + courseCode
            + " 缺少快照级课程属性或来源，无法返回可信课程资料");
        this.snapshotId = snapshotId;
        this.courseCode = courseCode;
    }

    public String getSnapshotId() { return snapshotId; }
    public String getCourseCode() { return courseCode; }
}
