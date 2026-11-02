package com.coursepilot.verifier.persistence.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;

/** Records the normalized importer key so sequential retries reuse one published snapshot. */
@Entity
@Table(
    name = "curriculum_import_receipt",
    uniqueConstraints =
        @UniqueConstraint(name = "uk_curriculum_import_snapshot", columnNames = "snapshot_id"))
public class CurriculumImportReceipt {
    @Id
    @Column(length = 64)
    private String idempotencyKey;

    @Column(nullable = false, length = 120)
    private String snapshotId;

    @Column(nullable = false, length = 120)
    private String trackId;

    @Column(nullable = false, length = 64)
    private String workbookHash;

    @Column(nullable = false)
    private Instant publishedAt;

    protected CurriculumImportReceipt() {}

    public CurriculumImportReceipt(
        String idempotencyKey, String snapshotId, String trackId,
        String workbookHash, Instant publishedAt) {
        this.idempotencyKey = idempotencyKey;
        this.snapshotId = snapshotId;
        this.trackId = trackId;
        this.workbookHash = workbookHash;
        this.publishedAt = publishedAt;
    }

    public String getIdempotencyKey() { return idempotencyKey; }
    public String getSnapshotId() { return snapshotId; }
    public String getTrackId() { return trackId; }
    public String getWorkbookHash() { return workbookHash; }
    public Instant getPublishedAt() { return publishedAt; }
}
