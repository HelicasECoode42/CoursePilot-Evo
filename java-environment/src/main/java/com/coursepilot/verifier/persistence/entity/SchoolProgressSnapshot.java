package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.time.Instant;

/** Source-faithful school report snapshot. JSON preserves category parent/child ids. */
@Entity
@Table(name = "school_progress_snapshot", uniqueConstraints = @UniqueConstraint(
    name = "uq_school_progress_subject_hash", columnNames = {"subject_id", "content_hash"}))
public class SchoolProgressSnapshot {
    @Id
    @Column(length = 120)
    private String schoolProgressId;

    @Column(name = "subject_id", nullable = false, length = 120)
    private String subjectId;

    @Column(name = "content_hash", nullable = false, length = 64)
    private String contentHash;

    @Column(nullable = false)
    private Instant importedAt;

    @Lob
    @Column(nullable = false)
    private String snapshotJson;

    @Lob
    @Column(nullable = false)
    private String academicRecordJson;

    protected SchoolProgressSnapshot() {}

    public SchoolProgressSnapshot(String id, String subjectId, String contentHash,
                                  Instant importedAt, String snapshotJson,
                                  String academicRecordJson) {
        this.schoolProgressId = id;
        this.subjectId = subjectId;
        this.contentHash = contentHash;
        this.importedAt = importedAt;
        this.snapshotJson = snapshotJson;
        this.academicRecordJson = academicRecordJson;
    }

    public String getSchoolProgressId() { return schoolProgressId; }
    public String getSubjectId() { return subjectId; }
    public String getContentHash() { return contentHash; }
    public Instant getImportedAt() { return importedAt; }
    public String getSnapshotJson() { return snapshotJson; }
    public String getAcademicRecordJson() { return academicRecordJson; }
}
